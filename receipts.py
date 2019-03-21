"""Receipts - A tool for automating screen grabs from twitter."""

import argparse
import ConfigParser
import functools
import io
import json
import logging
import os
import Queue as queue
import sys
import time

from threading import Thread

import twitter

log = logging.getLogger('receipts')
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(name)s - %(levelname)s - %(message)s')

try:
	from selenium import webdriver
except ImportError:
	log.warning('Screen-grab require selenium to be installed.')
	webdriver = None


# Globals #####################################################################

if not os.path.exists('config.ini'):
	raise IOError('Config file (config.ini) not found.')
try:
	config = ConfigParser.ConfigParser()
	config.read('config.ini')

except Exception:
	log.error('Failed to find or parse the config file.')
	raise

try:
	api = twitter.Api(
		consumer_key=config.get('twitter', 'consumer_key'),
		consumer_secret=config.get('twitter', 'consumer_secret'),
		access_token_key=config.get('twitter', 'access_token_key'),
		access_token_secret=config.get('twitter', 'access_token_secret'))

except Exception:
	log.error('Failed to connect to Twitter. Please check your config.')
	raise


CHROME_DRIVER = config.get('selenium', 'chrome_driver')

global ARCHIVE_LOCATION


# Helpers #####################################################################

def keep_alive(func):
	"""Decorator to keep retying the function on exceptions."""
	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		backoff = 4
		while True:
			try:
				result = func(*args, **kwargs)
				backoff = 2
				return result
			except (twitter.error.TwitterError, IOError):
				log.exception('Stream dropped, restarting.')
				time.sleep(backoff)
				backoff ** 2

	return wrapper


def capture_screen(driver, statuses):
	"""Capture tweet to a json blob and take a screen-grab."""
	for s in statuses:
		screen_name = s.user.screen_name
		
		image_path = os.path.join(ARCHIVE_LOCATION, screen_name, 'images')
		if not os.path.exists(image_path):
			os.makedirs(image_path)

		url = 'https://twitter.com/{screen_name}/status/{id}'.format(screen_name=screen_name, id=s.id)
	
		image_file = os.path.join(image_path, '{id}.png'.format(id=s.id))
		if not os.path.exists(image_file):
			driver.get(url)
			time.sleep(0.2)  # Let the user actually see something!
			driver.save_screenshot(image_file)


def capture_json(statuses):
	"""Capture tweet data to a json blob."""
	for s in statuses:
		screen_name = s.user.screen_name

		status_path = os.path.join(ARCHIVE_LOCATION, screen_name, 'status')
		if not os.path.exists(status_path):
			os.makedirs(status_path)

		json_file = os.path.join(status_path, '{id}.json'.format(id=s.id))
		if not os.path.exists(json_file):
			json_string = json.dumps(s.AsDict(), ensure_ascii=False, encoding='utf8', sort_keys=True)
			with io.open(json_file, 'w', encoding="utf-8") as fh:
				fh.write(json_string)


# Workers #####################################################################

@keep_alive
def track(stream_queue, track):
	"""Track a hash tag or search term."""
	for term in track:
		log.info('Watching for tweets containing to %s' % term)
	stream = api.GetStreamFilter(track=track)
	for line in stream:
		# Signal that the line represents a tweet
		if 'in_reply_to_status_id' in line:
			status = twitter.Status.NewFromJsonDict(line)
			log.debug('%s: %s', status.user.screen_name, status.text)
			stream_queue.put(status)
	

@keep_alive
def follow(stream_queue, screen_names):
	"""Follow specific users."""
	for user in screen_names:
		log.info('Watching for tweets related to @%s' % user)
	ids = [str(api.GetUser(screen_name=user).id) for user in screen_names]
	stream = api.GetStreamFilter(follow=ids)
	for line in stream:
		# Signal that the line represents a tweet
		if 'in_reply_to_status_id' in line:
			status = twitter.Status.NewFromJsonDict(line)
			log.debug('%s: %s', status.user.screen_name, status.text)
			stream_queue.put(status)


def process_screen_grabs(stream_queue):
	"""Process the queue of tweets."""
	if not webdriver:
		raise RuntimeError('Screen-grabs not avaiable. Please install selenium.')

	driver = webdriver.Chrome(CHROME_DRIVER)  # Optional argument, if not specified will search path.
	try:
		while True:
			try:
				status = stream_queue.get(True, 1)
			except queue.Empty:
				continue

			try:
				capture_screen(driver, [status])
				capture_json([status])
			except Exception:
				log.exception('Failed to process a tweet.')
	finally:
		driver.quit()


def process_json(stream_queue):
	"""Process the queue of tweets."""
	while True:
		try:
			status = stream_queue.get(True, 1)
		except queue.Empty:
			continue

		try:
			capture_json([status])
		except Exception:
			log.exception('Failed to process a tweet.')
	

# Entry point #################################################################

def build_parser():
	"""Build the command line argument parser."""
	parser = argparse.ArgumentParser(description='Tool for capturing tweets from a set of users or topics.', epilog='Use ctrl-c to close the script.')
	
	group = parser.add_argument_group('Twitter stream')
	group.add_argument(
		"-f",
		"--follow",
		nargs='+',
		help="One or more user names to follow")

	group.add_argument(
		"-t",
		"--track",
		nargs='+',
		help="One or terms or hashtags to track")

	parser.add_argument(
		"--image",
		action='store_true',
		help="Store screen-grabs as well as JSON blobs")

	parser.add_argument(
		"--archive",
		nargs='?',
		default='receipts',
		help="Location to store the data in")

	parser.add_argument(
		"--verbose",
		action='store_true',
		default=False,
		help="Display tweets as they come in.")

	return parser

if __name__ == '__main__':

	parser = build_parser()
	args = parser.parse_args()

	if args.verbose:
		log.setLevel(logging.DEBUG)

	stream_queue = queue.Queue(maxsize=0)

	# Start up a worker for each stream we are consuming.
	stream_up = False
	if args.track:
		terms = args.track  # ['#Christchurch', '#CHCH', ]
		track_worker = Thread(target=track, args=(stream_queue, terms))
		track_worker.setDaemon(True)
		track_worker.start()
		stream_up = True

	if args.follow:
		users = [u.lstrip('@') for u in args.follow]  # ['SeanPlunket', 'JudithCollinsMP', 'simonjbridges', 'dpfdpf']
		follow_worker = Thread(target=follow, args=(stream_queue, users))
		follow_worker.setDaemon(True)
		follow_worker.start()
		stream_up = True

	if not stream_up:
		raise parser.error('At least one of the arguments is required.')

	global ARCHIVE_LOCATION
	ARCHIVE_LOCATION = args.archive

	# Process the streams until we get a keyboard interupt.
	if args.image:
		process_screen_grabs(stream_queue)
	else:
		process_json(stream_queue)
