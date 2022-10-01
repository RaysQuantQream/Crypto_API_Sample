import smtplib
from email.mime.text import MIMEText


class email_send(object):

    def __init__(self, user_name=None, password=None, sender=None, receiver_list=None, title=None, text=None):
        self.mail_host = 'smtp.163.com'
        # self.mail_host = 'localhost'
        self.user_name = user_name
        self.password = password
        self.sender = sender
        self.receiver_list = receiver_list
        self.title = title
        self.text = text
        self.retry = 10

    def send(self):
        for receiver in self.receiver_list:
            message = MIMEText(self.text, 'plain', 'utf-8')
            # 邮件主题
            message['Subject'] = self.title
            # 发送方信息
            message['From'] = self.sender
            # 接受方信息
            message['To'] = receiver

            # 登录并发送邮件
            for i in range(self.retry):
                try:
                    smtpObj = smtplib.SMTP_SSL(self.mail_host, 465)
                    # 登录到服务器
                    smtpObj.login(self.user_name, self.password)
                    # 发送
                    smtpObj.sendmail(self.sender, receiver, message.as_string())
                    # 退出
                    smtpObj.quit()
                    print('邮件已发送')
                    return

                except smtplib.SMTPException as e:
                    print('error', e)  # 打印错误
                    continue
            print('多次尝试失败')
            return


if __name__ == '__main__':
    # 用户名
    user_name = 'pythonsende'
    # 密码（授权码）
    password = 'OMYZCVWPVBBAZXNO'
    # 邮箱地址
    sender = 'pythonsende@163.com'
    # 收信方地址列表
    # receiver_list = ['fukufukulee@gmail.com']
    receiver_list = ['249290248@qq.com']
    title = ''
    text = ''
    # 邮件主题
    email_send = email_send(user_name=user_name, password=password, sender=sender, receiver_list=receiver_list, title=title, text=text)
    # 邮件内容
    email_send.send()
