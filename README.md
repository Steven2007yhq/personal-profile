# personal-profile

袁华卿 (Steve) 的个人主页 —— Flask + 登录注册 + 几个纯前端小游戏。

## 本地运行

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
set SECRET_KEY=随便一串长字符      # macOS / Linux: export SECRET_KEY=...
python app.py
```

打开 http://127.0.0.1:8080/ ，会跳到登录页；点「去注册」建一个账号即可。

不配 `DATABASE_URL` 时用本地 SQLite 文件 `app.db`，已在 `.gitignore` 里。

## 页面

| 路径 | 说明 |
| --- | --- |
| `/login` `/register` `/logout` | 认证 |
| `/` | 个人主页（需登录） |
| `/story` | 个人经历（需登录） |
| `/games` `/games/<tetris\|pinball\|reaction\|memory>` | 小游戏（需登录） |
| `/contact` | 联系方式（需登录） |

## 部署到 Render

**必须配一个外部数据库，否则注册的账号还是会丢。**

Render 免费套餐有两个限制，正好会让账号消失：

- Web 服务闲置 15 分钟就休眠，下次访问冷启动 = 进程重启
- 文件系统是临时的，重启和重新部署都会清空 —— SQLite 文件也保不住
- Render 自带的免费 PostgreSQL **30 天后过期**（+14 天宽限期），不适合长期用

所以推荐用一个外部的免费 PostgreSQL，比如 [Neon](https://neon.tech/) 或
[Supabase](https://supabase.com/)，拿到形如
`postgresql://用户:密码@主机/数据库` 的连接串。

然后在 Render 的服务里配两个环境变量：

| 变量 | 值 |
| --- | --- |
| `SECRET_KEY` | 让 Render 自动生成（`render.yaml` 里已设 `generateValue: true`） |
| `DATABASE_URL` | 上面那串 PostgreSQL 连接串 |

`render.yaml` 已经写好，`DATABASE_URL` 标了 `sync: false`，
需要你在 Render 控制台里手动填一次（避免连接串进仓库）。

> 换数据库不用改代码：`app.py` 里根据 `DATABASE_URL` 自动切换，
> 也会自动把 Render/Heroku 给的 `postgres://` 修正成 SQLAlchemy 要的 `postgresql://`。

## 这次改了什么

原来的实现有三个问题，合起来导致「注册完，下次登录进不去」：

1. **用户存在进程内存的字典里**（`users = {'admin': 'password'}`）。
   服务一休眠/重启/重新部署，注册的账号就没了；gunicorn 多 worker 时
   各 worker 各有一份，在 A 注册、请求落到 B 也登录不上。
   → 改为数据库存储。
2. **登录形同虚设**：登录成功后 `redirect` 到 `/static/index (2).html`，
   而 `static/` 是公开目录，任何人直接敲这个地址就能跳过登录看到全部内容。
   → 页面移到 `templates/`，一律 `render_template`；`static/` 不再放受保护内容。
3. **密码明文存储**，`secret_key` 硬编码成 `'your_secret_key'` 提交在公开仓库里
   （等于谁都能伪造任意用户的登录态），登录页上还直接印着 `admin / password`。
   → 密码改用 scrypt 哈希；`SECRET_KEY` 从环境变量读；默认账号和提示已移除。

顺带补上的：注册时的用户名/密码校验和确认密码、用户名大小写不敏感、
注册后自动登录、登录后跳回原本要去的页面、CSRF 防护、
登录失败不区分「用户不存在」和「密码错误」（避免被拿去探测已注册用户名）、
中文 404 页、旧链接 `/my story` 和 `/static/*.html` 的兼容跳转。

## 测试

```bash
.venv\Scripts\python _test_auth.py       # 32 项：拦截、注册校验、登录、CSRF、哈希
.venv\Scripts\python _test_restart.py register
.venv\Scripts\python _test_restart.py login    # 验证账号跨进程重启保留
```
