import os
import hashlib
import base64
import urllib
import logging
import feedparser
from google.appengine.api import xmpp
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import xmpp_handlers
from google.appengine.ext.webapp import template
from google.appengine.ext import db
from google.appengine.api import urlfetch


SUPERFEEDR_LOGIN = "XXXX"
SUPERFEEDR_PASSWORD = "YYYY"

##
# the function that sends subscriptions/unsubscriptions to Superfeedr
def superfeedr(mode, subscription):
  post_data = {
      'hub.mode' : mode,
      'hub.callback' : "http://notifixlite.appspot.com/hubbub/" + subscription.key().name(),
      'hub.topic' : subscription.feed, 
      'hub.verify' : 'sync',
      'hub.verify_token' : '',
  }
  base64string = base64.encodestring('%s:%s' % (SUPERFEEDR_LOGIN, SUPERFEEDR_PASSWORD))[:-1]
  form_data = urllib.urlencode(post_data)
  result = urlfetch.fetch(url="http://superfeedr.com/hubbub",
                  payload=form_data,
                  method=urlfetch.POST,
                  headers={"Authorization": "Basic "+ base64string, 'Content-Type': 'application/x-www-form-urlencoded'})
  return result


##
# The subscription model that matches a feed and a jid.
class Subscription(db.Model):
  feed = db.TextProperty(required=True)
  jid = db.TextProperty(required=True)
  created_at = db.DateTimeProperty(required=True, auto_now_add=True)

##
# The web app interface
class MainPage(webapp.RequestHandler):
  
  def Render(self, template_file, template_values = {}):
     path = os.path.join(os.path.dirname(__file__), 'templates', template_file)
     self.response.out.write(template.render(path, template_values))
  
  def get(self):
    self.Render("index.html")

##
# The HubbubSusbcriber
class HubbubSubscriber(webapp.RequestHandler):

  ##
  # Called upon notification
  def post(self, feed_sekret):
    subscription = Subscription.get_by_key_name(feed_sekret)
    
    body = self.request.body.decode('utf-8')
    logging.info('Post body is %d characters', len(body))

    data = feedparser.parse(self.request.body)
    if data.bozo:
      logging.error('Bozo feed data. %s: %r',
                     data.bozo_exception.__class__.__name__,
                     data.bozo_exception)
      if (hasattr(data.bozo_exception, 'getLineNumber') and
          hasattr(data.bozo_exception, 'getMessage')):
        line = data.bozo_exception.getLineNumber()
        logging.error('Line %d: %s', line, data.bozo_exception.getMessage())
        segment = self.request.body.split('\n')[line-1]
        logging.info('Body segment with error: %r', segment.decode('utf-8'))
      return self.response.set_status(500)

    logging.info('Found %d entries', len(data.entries))
    for entry in data.entries:
      entry_id = entry.id
      content = entry.content[0].value
      link = entry.get('link', '')
      title = entry.get('title', '')
      
      logging.info('Found entry with title = "%s", id = "%s", '
                   'link = "%s", content = "%s"',
                   title, entry_id, link, content)
      user_address = subscription.jid
      if xmpp.get_presence(user_address):
        msg = title + "\n" + content + "\n" + link
        status_code = xmpp.send_message(user_address, msg)
      
    self.response.set_status(200)
    self.response.out.write("Aight. Saved."); 
  
  def get(self, feed_sekret):
    self.response.out.write(self.request.get('hub.challenge'))
    self.response.set_status(200)
  
##
# The XMPP App interface
class XMPPHandler(xmpp_handlers.CommandHandler):
  
  # Asking to subscribe to a feed
  def subscribe_command(self, message=None):
    message = xmpp.Message(self.request.POST)
    subscriber = message.sender.rpartition("/")[0]
    subscription = Subscription(key_name=hashlib.sha224(message.arg + subscriber).hexdigest(), feed=message.arg, jid=subscriber)
    result = superfeedr("subscribe", subscription)
    if result.status_code == 204:
      subscription.put() # saves the subscription
      message.reply("Well done! You're subscribed to " + message.arg)
    else:
      message.reply("Sorry, couldn't susbcribe to " + message.arg)
    
  ##
  # Asking to unsubscribe to a feed
  def unsubscribe_command(self, message=None):
    message = xmpp.Message(self.request.POST)
    subscriber = message.sender.rpartition("/")[0]
    subscription = Subscription.get_by_key_name(hashlib.sha224(message.arg + subscriber).hexdigest())
    result = superfeedr("unsubscribe", subscription)
    if result.status_code == 204:
      subscription.delete() # saves the subscription
      message.reply("Well done! You're not subscribed anymore to " + message.arg)
    else:
      message.reply("Sorry :/, couldn't unsusbcribe from " + message.arg)

  ##
  # Asking for help
  def hello_command(self, message=None):
    message = xmpp.Message(self.request.POST)
    message.reply("Oh, Hai! This is a light version of http://notifixio.us : subscribe to your favorite feeds and get their updates via IM. For more infon type /help.")
    message.reply(message.body)
  
  ##
  # Asking for help
  def help_command(self, message=None):
    message = xmpp.Message(self.request.POST)
    message.reply("That's easy, just type /subscribe <url> or /unsubscribe <url>")
    message.reply(message.body)
  
  ##
  # All other commants
  def unhandled_command(self, message=None):
    message = xmpp.Message(self.request.POST)
    message.reply("Please, type /help for help.")
    message.reply(message.body)
  
  ##
  # Sent for any message.
  def text_message(self, message=None):
    message = xmpp.Message(self.request.POST)
    message.reply("Echooooo (when you're done playing, type /help) > " + message.body)

application = webapp.WSGIApplication([('/_ah/xmpp/message/chat/', XMPPHandler), ('/', MainPage), ('/hubbub/(.*)', HubbubSubscriber)],debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
  
