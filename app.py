from flask import Flask, render_template, request, redirect, url_for, session
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # 用于会话管理的密钥

# 简单的用户数据库（实际应用中应使用更安全的存储方式）
users = {
    'admin': 'password'  # 用户名: 密码
}

@app.route('/')
def index():
    # 检查用户是否已登录
    if 'username' in session:
        # 登录状态，重定向到index(2).html
        return redirect(url_for('static', filename='index (2).html'))
    else:
        # 未登录，重定向到登录页面
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # 验证用户凭据
        if username in users and users[username] == password:
            # 登录成功，设置会话
            session['username'] = username
            # 重定向到index(2).html
            return redirect(url_for('static', filename='index (2).html'))
        else:
            # 登录失败，显示错误信息
            return render_template('login.html', error='Invalid username or password')
    else:
        # GET请求，显示登录页面
        return render_template('login.html')

@app.route('/logout')
def logout():
    # 清除会话
    session.pop('username', None)
    # 重定向到登录页面
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # 检查用户名是否已存在
        if username in users:
            return render_template('register.html', error='Username already exists')
        else:
            # 注册新用户
            users[username] = password
            # 自动登录新用户
            session['username'] = username
            # 重定向到index(2).html
            return redirect(url_for('static', filename='index (2).html'))
    else:
        # GET请求，显示注册页面
        return render_template('register.html')

@app.route('/games')
def games():
    # 检查用户是否已登录
    if 'username' in session:
        # 登录状态，重定向到games.html
        return redirect(url_for('static', filename='games.html'))
    else:
        # 未登录，重定向到登录页面
        return redirect(url_for('login'))

@app.route('/contact')
def contact():
    # 检查用户是否已登录
    if 'username' in session:
        # 登录状态，重定向到contact.html
        return redirect(url_for('static', filename='contact.html'))
    else:
        # 未登录，重定向到登录页面
        return redirect(url_for('login'))

@app.route('/games/<game>')
def game(game):
    # 检查用户是否已登录
    if 'username' in session:
        # 登录状态，重定向到对应的游戏页面
        return redirect(url_for('static', filename=f'{game}.html'))
    else:
        # 未登录，重定向到登录页面
        return redirect(url_for('login'))

@app.route('/my story')
def my_story():
    # 检查用户是否已登录
    if 'username' in session:
        # 登录状态，重定向到my story.html
        return redirect(url_for('static', filename='my story.html'))
    else:
        # 未登录，重定向到登录页面
        return redirect(url_for('login'))

if __name__ == '__main__':
    # 确保static文件夹存在
    if not os.path.exists('static'):
        os.makedirs('static')
    # 启动Flask应用，使用8080端口
    app.run(debug=True, port=8080, host='0.0.0.0')