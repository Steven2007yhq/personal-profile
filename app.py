"""
个人主页 —— 登录 / 注册

原来的实现有几个问题，都会直接导致「注册完，下次登录进不去」：

1. 用户存在进程内存的字典里。Render 免费服务闲置 15 分钟就休眠，
   下次访问冷启动 = 进程重启 = 字典清空，注册过的账号全没了；
   gunicorn 多 worker 时各自一份字典，在 A 注册、请求落到 B 也登录不上。
   -> 改为数据库存储。
2. 登录成功后 redirect 到 /static/index (2).html。static 目录是公开的，
   任何人直接敲这个地址就能跳过登录，整套鉴权形同虚设。
   -> 页面移到 templates/，一律 render_template，静态目录不再放受保护内容。
3. 密码明文存储、secret_key 硬编码在公开仓库里（等于谁都能伪造登录态）。
   -> 密码改为 scrypt 哈希，SECRET_KEY 从环境变量读。
"""

import os
import re
import secrets
from datetime import timedelta
from functools import wraps
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import (
    Flask, abort, flash, g, redirect, render_template,
    request, session, url_for,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


def _database_uri() -> str:
    """
    优先用环境变量 DATABASE_URL（Render / Neon / Supabase 都是给这个）。
    没配就退回本地 SQLite，方便本地开发。

    注意：Render 免费套餐的磁盘是临时的，SQLite 文件重启就没了。
    要真正持久必须配一个外部数据库，见 README。
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return "sqlite:///" + os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")

    # Render / Heroku 给的是 postgres://，SQLAlchemy 2.x 只认 postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # 远程 PostgreSQL 自动补 sslmode=require。
    # Neon / Supabase 都强制 SSL，但它们给的连接串里那个 "?sslmode=require"
    # 带了个等号，粘进 Render 的环境变量 Key 输入框时会被按 "=" 拆开，
    # 很容易配错。这里自动补上，连接串就可以只填到数据库名为止。
    if url.startswith("postgresql://"):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        if "sslmode" not in query and (parts.hostname or "") not in LOCAL_HOSTS:
            query["sslmode"] = "require"
            url = urlunsplit(parts._replace(query=urlencode(query)))
    return url


def create_app() -> Flask:
    app = Flask(__name__)

    secret = os.environ.get("SECRET_KEY", "").strip()
    if not secret:
        # 本地开发临时用随机值：进程重启后登录态失效，但不会像硬编码那样泄露。
        secret = secrets.token_hex(32)
        app.logger.warning(
            "未设置 SECRET_KEY，本次使用随机密钥；重启后所有人需要重新登录。"
            "部署环境请务必配置 SECRET_KEY 环境变量。"
        )
    app.config.update(
        SECRET_KEY=secret,
        SQLALCHEMY_DATABASE_URI=_database_uri(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        # 连接池里的连接被数据库单方面掐断时自动重连（免费实例常见）
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # 线上走 HTTPS 时把 cookie 标记为仅 HTTPS
        SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") != "development",
    )

    db.init_app(app)
    with app.app_context():
        db.create_all()

    register_routes(app)
    return app


# --------------------------------------------------------------------------
# 数据模型
# --------------------------------------------------------------------------
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    # 登录时大小写不敏感，这里存规范化后的小写用于查重和查询
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    # 保留用户注册时输入的原始大小写，用于展示
    display_name = db.Column(db.String(32), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)

    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,20}$")
PASSWORD_MIN = 8


def validate_username(name: str):
    if not name:
        return "请填写用户名"
    if not USERNAME_RE.match(name):
        return "用户名需为 3–20 位，只能用字母、数字、下划线或连字符"
    return None


def validate_password(pw: str, confirm: str):
    if not pw:
        return "请填写密码"
    if len(pw) < PASSWORD_MIN:
        return f"密码至少 {PASSWORD_MIN} 位"
    if pw != confirm:
        return "两次输入的密码不一致"
    return None


# --------------------------------------------------------------------------
# 登录态 / CSRF
# --------------------------------------------------------------------------
def current_user():
    """把当前用户缓存在 g 上，一个请求内只查一次库。"""
    if "user" not in g:
        uid = session.get("user_id")
        g.user = db.session.get(User, uid) if uid else None
    return g.user


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            # 记住原本想去的页面，登录后跳回去
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapper


def csrf_token() -> str:
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def check_csrf() -> None:
    sent = request.form.get("_csrf", "")
    if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
        abort(400, description="表单已过期，请刷新页面重试")


def safe_next(target: str) -> str:
    """只允许跳转到本站的相对路径，避免开放重定向。"""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("home")


# --------------------------------------------------------------------------
# 路由
# --------------------------------------------------------------------------
def register_routes(app: Flask) -> None:

    @app.context_processor
    def inject_globals():
        return {"current_user": current_user(), "csrf_token": csrf_token}

    # ---------------- 认证 ----------------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user():
            return redirect(url_for("home"))

        if request.method == "POST":
            check_csrf()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            user = User.query.filter_by(username=username.lower()).first()
            if user is None or not user.check_password(password):
                # 不区分「用户不存在」和「密码错误」，避免被用来探测已注册用户名
                return render_template(
                    "login.html", error="用户名或密码不正确", username=username
                ), 401

            session.clear()
            session["user_id"] = user.id
            session.permanent = True
            return redirect(safe_next(request.args.get("next", "")))

        return render_template("login.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user():
            return redirect(url_for("home"))

        if request.method == "POST":
            check_csrf()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm", "")

            error = validate_username(username) or validate_password(password, confirm)
            if error is None and User.query.filter_by(username=username.lower()).first():
                error = "这个用户名已经被注册了"

            if error:
                return render_template("register.html", error=error, username=username), 400

            user = User(username=username.lower(), display_name=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            # 注册完直接登录，不用再输一遍
            session.clear()
            session["user_id"] = user.id
            session.permanent = True
            flash(f"欢迎，{user.display_name}！账号已创建。")
            return redirect(url_for("home"))

        return render_template("register.html")

    @app.route("/logout", methods=["POST"])
    def logout():
        check_csrf()
        session.clear()
        return redirect(url_for("login"))

    # ---------------- 受保护页面 ----------------
    # 这些页面原来放在 static/ 下，靠 redirect 过去，等于没有鉴权。
    # 现在从 templates/ 渲染，未登录拿不到内容。
    @app.route("/")
    @login_required
    def home():
        return render_template("home.html")

    @app.route("/story")
    @login_required
    def story():
        return render_template("story.html")

    @app.route("/games")
    @login_required
    def games():
        return render_template("games.html")

    @app.route("/contact")
    @login_required
    def contact():
        return render_template("contact.html")

    GAMES = {"tetris", "pinball", "reaction", "memory"}

    @app.route("/games/<game>")
    @login_required
    def game(game):
        if game not in GAMES:
            abort(404)
        return render_template(f"{game}.html")

    # ---------------- 旧地址兼容 ----------------
    # 老链接里带空格的 /my story，以及直接指向静态文件的地址，统一收敛过来
    @app.route("/my story")
    @app.route("/my%20story")
    def legacy_story():
        return redirect(url_for("story"), code=301)

    @app.route("/static/<path:filename>")
    def legacy_static(filename):
        if filename.endswith(".html"):
            return redirect(url_for("home"), code=301)
        abort(404)

    # ---------------- 错误页 ----------------
    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404,
                               message="这个页面不存在"), 404

    @app.errorhandler(400)
    def bad_request(e):
        return render_template("error.html", code=400,
                               message=getattr(e, "description", "请求有误")), 400


app = create_app()


if __name__ == "__main__":
    # 本地调试用；线上由 gunicorn 启动（见 render.yaml），不会走到这里
    app.run(host="127.0.0.1", port=8080, debug=True)
