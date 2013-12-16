'''
Created on 13-Dec-2013

@author: someshs
'''
import sys
sys.dont_write_bytecode = True

from requires.base import BaseHandler, authenticated
from asyncmail import AsycnEmail
from requires.settings import SETTINGS

class FeedbackHandler(BaseHandler):
       
    SUPPORTED_METHODS = ('POST',)
    REQUIRED_FIELDS = {
        'POST': ('message',),
        }

    @authenticated
    def post(self, *args, **kwargs):
        if not self.get_argument('message'):
            self.send_error(404)
        async_email = AsycnEmail(self.request)
        template = SETTINGS['template_path']+'/'+'feedback_mailtemplate.html'
        params={'message': self.get_argument('message'),
                'user': self.current_user.username}
        async_email.generate_subject_content(
                     subject='Feedback from %s' %(self.current_user.username))
        async_email.send_email(email=SETTINGS['feedback_email'],
                               template=template,
                               params=params,
                               from_email=self.current_user.email,
                               reply_to=self.current_user.email)
        response = {'status': 200,
                    'message': 'Feedback submitted successfully'
                    }
        self.write(response)