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
from google.appengine.runtime import apiproxy_errors
from google.appengine.api.app_identity import get_application_id

SUPERFEEDR_LOGIN = ""
SUPERFEEDR_PASSWORD = ""
appname = get_application_id()

##
# the function that sends subscriptions/unsubscriptions to Superfeedr
def superfeedr(mode, subscription):
  post_data = {
      'hub.mode' : mode,
      'hub.callback' : "http://" + appname + ".appspot.com/hubbub/" + subscription.key().name(),
      'hub.topic' : subscription.feed,
      'hub.verify' : 'async',
      'hub.verify_token' : '',
  }
  base64string = base64.encodestring('%s:%s' % (SUPERFEEDR_LOGIN, SUPERFEEDR_PASSWORD))[:-1]
  form_data = urllib.urlencode(post_data)
  result = urlfetch.fetch(url="http://superfeedr.com/hubbub",
                  payload=form_data,
                  method=urlfetch.POST,
                  headers={"Authorization": "Basic "+ base64string, 'Content-Type': 'application/x-www-form-urlencoded'},
                  deadline=10)
  # logging.info('Result of %s to %s => %s (%d)',mode, subscription.feed, result.content, result.status_code )

  return result


##
# The subscription model that matches a feed and a jid.
class Subscription(db.Model):
  feed = db.LinkProperty(required=True)
  jid = db.StringProperty(required=True)
  created_at = db.DateTimeProperty(required=True, auto_now_add=True)

##
# The web app interface
class MainPage(webapp.RequestHandler):

  def Render(self, template_file, template_values = {'appname': appname}):
     path = os.path.join(os.path.dirname(__file__), 'templates', template_file)
     self.response.out.write(template.render(path, template_values))

  def get(self):
    self.redirect('http://blog.superfeedr.com/notifixlight/')

##
# The HubbubSusbcriber
class HubbubSubscriber(webapp.RequestHandler):

  ##
  # Called upon notification
  def post(self, feed_sekret):
    subscription = None
    try: subscription = Subscription.get_by_key_name(feed_sekret)
    except apiproxy_errors.OverQuotaError, error_message:
      logging.error(error_message)
      pass
    if(subscription == None):
      if self.request.get("hub.mode") == "unsubscribe" :
        # Let superfeedr unsusbscribe this.
        # Even though we have no record of it.
        self.response.set_status(200)
        self.response.out.write(self.request.get('hub.challenge'))
      else:
        self.response.set_status(404)
        self.response.out.write("Sorry, no feed.");
    else:
      body = self.request.body.decode('utf-8')
      data = feedparser.parse(self.request.body)
      # logging.info('Found %d entries in %s', len(data.entries), subscription.feed)
      feed_title = data.feed.title
      for entry in data.entries:
        link = entry.get('link', '')
        title = entry.get('title', '')
        # logging.info('Found entry with title = "%s", '
        #            'link = "%s"',
        #            title, link)
        user_address = subscription.jid
        msg = "'" + feed_title + "' : " + title + "\n" + link
        status_code = xmpp.send_message(user_address, msg)
      self.response.set_status(200)
      self.response.out.write("Alright. Saved.");

  def get(self, feed_sekret):
    subscription = None
    try: subscription = Subscription.get_by_key_name(feed_sekret)
    except apiproxy_errors.OverQuotaError, error_message:
      logging.error(error_message)
      pass
    if(subscription == None):
      if self.request.get("hub.mode") == "unsubscribe" :
        # Let superfeedr unsusbscribe this.
        # Even though we have no record of it.
        self.response.set_status(200)
        self.response.out.write(self.request.get('hub.challenge'))
      else:
        self.response.set_status(404)
        self.response.out.write("Sorry, no feed.");
    else:
      # Let's confirm to the subscriber that he'll get notifications for this feed.
      user_address = subscription.jid
      if(self.request.get("hub.mode") == "subscribe"):
        msg =  "You're now subscribed to " + subscription.feed
        xmpp.send_message(user_address, msg)
        self.response.out.write(self.request.get('hub.challenge'))
        self.response.set_status(200)
      elif(self.request.get("hub.mode") == "unsubscribe"):
        msg =  "You're not anybmore subscribed to " + subscription.feed
        xmpp.send_message(user_address, msg)
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
    subscription.put() # saves the subscription
    result = superfeedr("subscribe", subscription)
    if result.status_code == 204:
      # logging.info("Subscription success! %s", message.arg)
      message.reply("Successfully subscribed to " + message.arg + "!")
    elif result.status_code == 202:
      message.reply("Subscribing to " + message.arg + ", you should get a confirmation soon.")
    else:
      message.reply("Could not subscribe to " + message.arg + ", looks like AppEngine got a small glitch. Please try again!")
      logging.error("Sorry, couldn't subscribe ( Status %s - Error %s) to %s",  message.arg, result.status_code, result.content)

  ##
  # Asking to unsubscribe to a feed
  def unsubscribe_command(self, message=None):
    message = xmpp.Message(self.request.POST)
    subscriber = message.sender.rpartition("/")[0]
    if message.arg == "all":
      query = Subscription.all().filter("jid =",subscriber).order("feed")
      subscriptions =  query.fetch(query.count() + 1)
      for subscription in subscriptions:
        subscription.delete()
      db.delete(subscriptions)
      message.reply("Well done! We deleted all your subscriptions!")
    else :
      subscription = Subscription.get_by_key_name(hashlib.sha224(message.arg + subscriber).hexdigest())
      if(subscription == None):
        message.reply("Looks like you were not susbcribed to " + message.arg)
      else:
        result = superfeedr("unsubscribe", subscription)
        subscription.delete() # deletes the subscription
        message.reply("Well done! You're not subscribed anymore to " + message.arg)

  ##
  # List subscriptions by page
  # 100/page
  # page default to 1
  def list_command(self, message=None):
    message = xmpp.Message(self.request.POST)
    subscriber = message.sender.rpartition("/")[0]
    query = Subscription.all().filter("jid =",subscriber).order("feed")
    count = query.count()
    if count == 0:
      message.reply("Seems you subscribed nothing yet. Type\n  /subscribe http://twitter.com/statuses/user_timeline/43417156.rss\nto play around.")
    else:
      page_index = int(message.arg or 1)
      if count%100 == 0:
        pages_count = count/100
      else:
        pages_count = count/100 + 1

      page_index = min(page_index, pages_count)
      offset = (page_index - 1) * 100
      subscriptions = query.fetch(100, offset)
      message.reply("Your have %d subscriptions in total: page %d/%d \n" % (count,page_index,pages_count))
      feed_list = [s.feed for s in subscriptions]
      message.reply("\n".join(feed_list))

  ##
  # Asking for help
  def hello_command(self, message=None):
    message = xmpp.Message(self.request.POST)
    message.reply("Oh, Hai! " + appname
                  + " is a small app to help you subscribe to your favorite feeds and get their updates via IM. It's powered by Superfeedr (http://superfeedr.com) and its magic powers!. ")
    message.reply("Make it better : http://github.com/superfeedr/notifixlight.")
    message.reply("For more info, type /help.")

  ##
  # Asking for help
  def help_command(self, message=None):
    message = xmpp.Message(self.request.POST)
    help_msg = "It's not even alpha ready, but you could play with following commands:\n\n" \
               "/hello -> about me\n\n" \
	       "/subscribe <url>\n/unsubscribe <url|'all'> -> subscribe or unsubscribe to a feed\n\n" \
	       "/list <page_index> ->  list subscriptions, default to page 1\n\n" \
	       "/help ->  get help message\n"
    message.reply(help_msg)
    message.reply(message.body)

  ##
  # All other commants
  def unhandled_command(self, message=None):
    message = xmpp.Message(self.request.POST)
    message.reply("Please, type /help for help.")

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

