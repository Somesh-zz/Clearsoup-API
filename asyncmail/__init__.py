'''
Created on 22-Aug-2013

@author: someshs
'''

import sys
from tornado.web import RequestHandler
sys.dont_write_bytecode = True

from tornadomail.message import EmailMessage, EmailMultiAlternatives,\
    EmailFromTemplate
from requires.settings import ClearSoupApp


class AsycnEmail(ClearSoupApp):
    '''
    handler for sending async email. 
    
    '''
    def __init__(self, *args, **kwargs):
        self._subject = None
        self._message = None
        self._user = None

    def generate_publish_content(self, user=None):
        '''
        Generate subject and message body when a url is being shared
        '''
        self._subject = 'Welcome to Clearsoup'
        self._message = 'Mr. ' + user.username + '\n'
        self._message = self._message.join(['', 'Thanks\n Team Clearsoup'])

    def generate_invite_content(self, message=None):
        self._subject = "You are invited to join Clearsoup"
        self._message = message
    
    def generate_new_account_content(self):
        '''
        Generate subject and message body when user is signing up for the
        first time.
        '''
        self._subject = ''
        self._message = ''
    
    def send_email(self, email):
        try:
            message = EmailMessage(
                self._subject,
                self._message,
                'No-Reply@clearsoup.in',
                [email],
                connection=self.mail_connection
            )
            message.send()
        except Exception, e:
            print e
