'''
Created on 13-Dec-2013

@author: someshs
'''

from feedback.handler import FeedbackHandler

URLS = [('/api/feedback/?$', FeedbackHandler),
       ]

__all__ = ['URLS']

