# -*- coding: utf-8 -*-
"""模拟 Render 休眠/重启：进程 A 注册，进程结束；进程 B 重新起来后还能登录。"""
import os, re, sys
os.environ['SECRET_KEY']='persistent-secret'; os.environ['FLASK_ENV']='development'
import app as appmod
def token(c,p):
    return re.search(r'name="_csrf" value="([^"]+)"', c.get(p).get_data(as_text=True)).group(1)
mode=sys.argv[1]
c=appmod.app.test_client()
if mode=='register':
    t=token(c,'/register')
    r=c.post('/register',data={'_csrf':t,'username':'restartuser','password':'longpassword1','confirm':'longpassword1'})
    print('  注册:', '成功' if r.status_code==302 else '失败 %s'%r.status_code)
else:
    t=token(c,'/login')
    r=c.post('/login',data={'_csrf':t,'username':'restartuser','password':'longpassword1'})
    okk = r.status_code==302
    print('  重启后登录:', '成功' if okk else '失败 %s'%r.status_code)
    if okk:
        h=c.get('/')
        print('  进入个人主页:', '成功' if (h.status_code==200 and '袁华卿' in h.get_data(as_text=True)) else '失败')
    sys.exit(0 if okk else 1)
