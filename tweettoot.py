#!/usr/bin/env python3

from mastodon import Mastodon
from Misskey import Misskey
from tweepy import API
from tweepy import OAuthHandler
import helpers
import html
import logging
import mimetypes
import os
import re
import requests
import tempfile

logger = logging.getLogger(__name__)

class TweetToot:
    app_name = ""
    twitter_url = ""
    mastodon_url = ""
    mastodon_token = ""
    twitter_user_id = 0
    twitter_api_key = ""
    twitter_api_secret = ""
    twitter_user_key = ""
    twitter_user_secret = ""
    tweet_amount = 1
    strip_urls = False
    include_rts = False
    misskey = False
    posted_ids = []
    remove_url_re = r'(https|http)?:\/\/(\w|\.|\/|\?|\=|\&|\%)*\b'
    twitter_username_re = re.compile(r'(?<=^|(?<=[^a-zA-Z0-9-\.]))@([A-Za-z0-9_]+)')
    logger_prefix = ""

    def __init__(self, app_name: str, twitter_url: str, mastodon_url: str, mastodon_token: str,
                twitter_user_id: str, twitter_api_key: str, twitter_api_secret: str, twitter_user_key: str,
                twitter_user_secret: str, strip_urls: bool, include_rts: bool, tweet_amount: int,
                misskey: bool):
        self.app_name = app_name
        self.twitter_url = twitter_url
        self.mastodon_url = mastodon_url
        self.mastodon_token = mastodon_token
        self.twitter_user_id = twitter_user_id
        self.twitter_api_key = twitter_api_key
        self.twitter_api_secret = twitter_api_secret
        self.twitter_user_key = twitter_user_key
        self.twitter_user_secret = twitter_user_secret
        self.strip_urls = strip_urls
        self.include_rts = include_rts
        self.posted_ids = self.read_posted_ids()
        self.tweet_amount = tweet_amount
        self.logger_prefix = self.app_name + " - "
        self.misskey = misskey

    def relay(self):
        if not self.app_name:
            logger.error(self.logger_prefix + "Application name in config is incorrect/empty.")
            return False

        if not self.twitter_url:
            logger.error(self.logger_prefix + "Twitter URL in config is incorrect/empty.")
            return False

        if not self.mastodon_url:
            logger.error(self.logger_prefix + "Mastodon URL in config is incorrect/empty.")
            return False

        if not self.mastodon_token:
            logger.error(self.logger_prefix + "Mastodon token in config is incorrect/empty.")
            return False
        # TODO: add more checks

        logger.info(self.logger_prefix + "Init relay from " + self.twitter_url + " to " + self.mastodon_url + ".")

        auth = OAuthHandler(self.twitter_api_key, self.twitter_api_secret)
        auth.set_access_token(self.twitter_user_key, self.twitter_user_secret)
        twitter_api = API(auth)

        timeline = self.get_latest_tweets(twitter_api, self.tweet_amount)
        for tweet in timeline:
            is_rt = hasattr(tweet, 'retweeted_status')

            if not self.include_rts and is_rt:
                logger.info(self.logger_prefix + "RT detected, skipping")
                continue

            tweet_id = tweet.id
            if str(tweet_id) in self.posted_ids:
                logger.info(self.logger_prefix + "Already posted, skipping (" + str(tweet_id) + ")")
                continue

            tweet_text = self.get_tweet_text(tweet, twitter_api, is_rt)
            tweet_text = html.unescape(tweet_text)
            tweet_text = self.escape_usernames(tweet_text)
            tweet_text = self.expand_urls(tweet, tweet_text, twitter_api, is_rt)

            if self.strip_urls:
                tweet_text = self.remove_urls(tweet_text)

            tweet_media = self.get_tweet_media(tweet, twitter_api, is_rt)

            if not self.misskey:
                # Only initialize the Mastodon API if we find something
                mastodon_api = Mastodon(
                    access_token=self.mastodon_token,
                    api_base_url=self.mastodon_url
                )

                media_ids = []
                for media in tweet_media:
                    media_id = self.transfer_media(media, mastodon_api)
                    if (media_id != -1):
                        media_ids.append(media_id);
                post_id = -1
                post_id = self.post_tweet(media_ids, tweet_text, tweet_id, mastodon_api)
                if (post_id != -1):
                    logger.info(self.logger_prefix + "Tweet posted to " + self.mastodon_url + " successfully (" + str(tweet_id) + ")!")
                    self.update_posted_ids(str(tweet_id))
                else:
                    logger.error(self.logger_prefix + "Failed to post Tweet to " + self.mastodon_url + " (" + str(tweet_id) + ")!")
            else:
                misskey = Misskey(self.mastodon_url, i=self.mastodon_token)
                media_ids = []
                for media in tweet_media:
                    media_id = self.transfer_media_misskey(media, misskey)
                    if (media_id != -1):
                        media_ids.append(media_id);
                post_id = -1
                post_id = misskey.notes_create(text=tweet_text, fileIds=media_ids)['createdNote']['id']
                if (post_id != -1):
                    logger.info(self.logger_prefix + "Tweet posted to " + self.mastodon_url + " successfully (" + str(tweet_id) + ")!")
                    self.update_posted_ids(str(tweet_id))
                else:
                    logger.error(self.logger_prefix + "Failed to post Tweet to " + self.mastodon_url + " (" + str(tweet_id) + ")!")

    def get_latest_tweets(self, twitter_api, amount):
        # count: maximum allowed tweets count
        # tweet_mode: extended to get the full text,it prevents a primary tweet longer than 140 characters from being truncated.
        timeline = twitter_api.user_timeline(user_id=self.twitter_user_id, count=amount, tweet_mode="extended")

        return timeline

    def get_tweet_entities(self, tweet, twitter_api, is_rt, get_ext=True):
        entities = None

        if is_rt:
            t = tweet._json['retweeted_status']
            if get_ext and 'extended_entities' in t:
                entities = t['extended_entities']
            elif 'entities' in t:
                entities = t['entities']
        elif get_ext and 'extended_entities' in tweet._json:
            entities = tweet.extended_entities
        elif 'entities' in tweet._json:
            entities = tweet.entities

        return entities

    def get_tweet_media(self, tweet, twitter_api, is_rt):
        media_list = []
        entities = self.get_tweet_entities(tweet, twitter_api, is_rt)

        if entities is None:
            return media_list

        if is_rt :
            if 'media' in entities:
                for media in entities['media']:
                    if media['type'] == 'video' or media['type'] == 'animated_gif':
                        media_list.append(self.get_best_media(media['video_info']['variants']))
                        break
                    else:
                        media_list.append(media['media_url'])
        elif 'media' in entities:
            for media in entities['media']:
                if media['type'] == 'video' or media['type'] == 'animated_gif':
                    media_list.append(self.get_best_media(media['video_info']['variants']))
                    break
                else:
                    media_list.append(media['media_url'])

        return media_list

    def get_best_media(self, media):
        higher_bitrate = -1
        media_url = ""

        for video in media:
            if (video['content_type'] == 'application/x-mpegURL'):
                continue

            if (video['bitrate'] > higher_bitrate):
                higher_bitrate = video['bitrate']
                media_url = video['url']

        return media_url

    def get_tweet_text(self, tweet, twitter_api, is_rt):
        text = ""
        remove_media_url = ""
        entities = self.get_tweet_entities(tweet, twitter_api, is_rt)

        if is_rt:
            t = tweet._json['retweeted_status']
            if 'full_text' in t:
                text = t['full_text']
            elif 'text' in t:
                text = t['text']

            text = "RT @" + t['user']['screen_name'] + ": " + text
        else:
            if hasattr(tweet, 'full_text'):
                text = tweet.full_text
            elif hasattr(tweet, 'text'):
                text = tweet.text

        if 'media' in entities:
            remove_media_url = entities['media'][0]['url']

        return text.replace(remove_media_url, "")

    def expand_urls(self, tweet, tweet_text, twitter_api, is_rt):
        text = tweet_text
        entities = self.get_tweet_entities(tweet, twitter_api, is_rt, False)

        if entities is None:
            return text

        if 'urls' in entities:
            for url in entities['urls']:
                text = text.replace(url['url'], url['expanded_url'])

        return text

    def transfer_media(self, media_url, mastodon_api):
        media_id = -1

        logger.info(self.logger_prefix + "Downloading " + media_url)

        media_file = requests.get(media_url, stream=True)
        media_file.raw.decode_content = True

        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.write(media_file.raw.read())
        temp_file.close()
        file_extension = mimetypes.guess_extension(media_file.headers['Content-type'])
        upload_file_name = temp_file.name + file_extension
        os.rename(temp_file.name, upload_file_name)
        temp_file_read = open(upload_file_name, 'rb')

        logger.info(self.logger_prefix + "Uploading " + media_url + " to " + self.mastodon_url)

        media_id = mastodon_api.media_post(upload_file_name)["id"]

        temp_file_read.close()
        os.unlink(upload_file_name)

        return media_id

    def transfer_media_misskey(self, media_url, misskey):
        media_id = -1

        logger.info(self.logger_prefix + "Downloading " + media_url)

        media_file = requests.get(media_url, stream=True)
        media_file.raw.decode_content = True

        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.write(media_file.raw.read())
        temp_file.close()
        file_extension = mimetypes.guess_extension(media_file.headers['Content-type'])
        upload_file_name = temp_file.name + file_extension
        os.rename(temp_file.name, upload_file_name)
        temp_file_read = open(upload_file_name, 'rb')

        logger.info(self.logger_prefix + "Uploading " + media_url + " to " + self.mastodon_url)

        media_id = misskey.drive_files_create(upload_file_name)["id"]

        temp_file_read.close()
        os.unlink(upload_file_name)

        return media_id

    def post_tweet(self, media_ids, tweet_text, tweet_id, mastodon_api):
        post = mastodon_api.status_post(
            status = tweet_text,
            media_ids = media_ids,
            visibility = "public",
            sensitive = False,
            spoiler_text = None,
            in_reply_to_id = None
        )

        return post["id"]

    def remove_urls(self, text):
        text = re.sub(self.remove_url_re, '', text, flags=re.MULTILINE)
        return text

    def read_posted_ids(self):
        lines = []
        with open("posted.ids") as file:
            for line in file:
                line = line.strip()
                lines.append(line)

        return lines

    def update_posted_ids(self, id):
        self.posted_ids.append(id)
        with open("posted.ids", "a") as file_object:
            file_object.write("\n" + id)

    def escape_usernames(self, text):
        ats = re.findall(self.twitter_username_re, text)
        for at in ats:
            text = text.replace("@"+at, "@*"+at)

        return text
