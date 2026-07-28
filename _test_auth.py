# -*- coding: utf-8 -*-
"""端到端验证：注册 -> 登出 -> 重新登录 -> 进入个人主页；以及未登录时的拦截。"""
import os, re, sys
os.environ['SECRET_KEY'] = 'test-secret-for-local-run'
os.environ['FLASK_ENV'] = 'development'
import app as appmod

ok = fail = 0
def check(label, cond, extra=''):
    global ok, fail
    if cond: ok += 1;  print('  PASS  %s' % label)
    else:    fail += 1; print('  FAIL  %s  %s' % (label, extra))

def token(c, path):
    html = c.get(path).get_data(as_text=True)
    m = re.search(r'name="_csrf" value="([^"]+)"', html)
    return m.group(1) if m else ''

client = appmod.app.test_client()

print('\n[1] 未登录时受保护页面应跳登录页')
for p in ['/', '/story', '/games', '/contact', '/games/tetris']:
    r = client.get(p)
    check('GET %s -> 302 /login' % p,
          r.status_code == 302 and '/login' in r.headers.get('Location',''),
          '实际 %s %s' % (r.status_code, r.headers.get('Location')))

print('\n[2] 旧的静态文件地址不能再绕过登录')
for p in ['/static/index (2).html', '/static/games.html', '/static/my story.html']:
    r = client.get(p)
    check('GET %r 不返回页面内容' % p, r.status_code in (301, 302, 404),
          '实际 %s' % r.status_code)

print('\n[3] 注册')
t = token(client, '/register')
r = client.post('/register', data={'_csrf': t, 'username': 'Steve', 'password': 'hunter2hunter2', 'confirm': 'hunter2hunter2'})
check('注册成功后跳转到主页', r.status_code == 302 and r.headers.get('Location','').endswith('/'),
      '实际 %s %s' % (r.status_code, r.headers.get('Location')))
r = client.get('/')
check('注册后可直接进入个人主页', r.status_code == 200 and '袁华卿' in r.get_data(as_text=True))

print('\n[4] 注册校验')
c2 = appmod.app.test_client()
cases = [
    ({'username':'Steve','password':'hunter2hunter2','confirm':'hunter2hunter2'}, '用户名已存在被拒绝'),
    ({'username':'ab','password':'hunter2hunter2','confirm':'hunter2hunter2'}, '用户名过短被拒绝'),
    ({'username':'bad name','password':'hunter2hunter2','confirm':'hunter2hunter2'}, '用户名含空格被拒绝'),
    ({'username':'newguy','password':'123','confirm':'123'}, '密码过短被拒绝'),
    ({'username':'newguy','password':'hunter2hunter2','confirm':'nomatch12345'}, '两次密码不一致被拒绝'),
]
for data, label in cases:
    t2 = token(c2, '/register'); data['_csrf'] = t2
    r = c2.post('/register', data=data)
    check(label, r.status_code == 400, '实际 %s' % r.status_code)

print('\n[5] 登出后再登录（关键路径）')
t = token(client, '/')
r = client.post('/logout', data={'_csrf': t})
check('登出跳登录页', r.status_code == 302 and '/login' in r.headers.get('Location',''))
check('登出后主页被拦截', client.get('/').status_code == 302)

t = token(client, '/login')
r = client.post('/login', data={'_csrf': t, 'username': 'Steve', 'password': 'hunter2hunter2'})
check('用注册的账号重新登录成功', r.status_code == 302, '实际 %s' % r.status_code)
r = client.get('/')
check('重新登录后进入个人主页', r.status_code == 200 and '袁华卿' in r.get_data(as_text=True))

print('\n[6] 用户名大小写不敏感')
c3 = appmod.app.test_client()
t3 = token(c3, '/login')
r = c3.post('/login', data={'_csrf': t3, 'username': 'STEVE', 'password': 'hunter2hunter2'})
check('大写用户名也能登录', r.status_code == 302, '实际 %s' % r.status_code)

print('\n[7] 错误密码 / CSRF')
c4 = appmod.app.test_client()
t4 = token(c4, '/login')
r = c4.post('/login', data={'_csrf': t4, 'username': 'Steve', 'password': 'wrongpassword'})
check('密码错误返回 401', r.status_code == 401, '实际 %s' % r.status_code)
check('错误提示不泄露用户是否存在', '用户名或密码不正确' in r.get_data(as_text=True))
r = c4.post('/login', data={'_csrf': 'forged', 'username': 'Steve', 'password': 'hunter2hunter2'})
check('伪造 CSRF token 被拒绝', r.status_code == 400, '实际 %s' % r.status_code)

print('\n[8] 密码是哈希存储，不是明文')
with appmod.app.app_context():
    u = appmod.User.query.filter_by(username='steve').first()
    check('库里查得到用户', u is not None)
    check('password_hash 不含明文', 'hunter2hunter2' not in (u.password_hash or ''))
    check('使用 scrypt/pbkdf2 哈希', u.password_hash.split(':')[0] in ('scrypt','pbkdf2'), u.password_hash[:20])

print('\n[9] 四个游戏页面登录后可访问')
for g in ['tetris','pinball','reaction','memory']:
    r = client.get('/games/%s' % g)
    check('/games/%s -> 200' % g, r.status_code == 200, '实际 %s' % r.status_code)
check('未知游戏返回 404', client.get('/games/nope').status_code == 404)

print('\n[10] 旧链接兼容')
r = client.get('/my story')
check('/my story -> 301 /story', r.status_code == 301 and '/story' in r.headers.get('Location',''))

print('\n========== %d passed, %d failed ==========' % (ok, fail))
sys.exit(1 if fail else 0)
