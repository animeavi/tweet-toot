#!/usr/bin/env python3

import helpers
import logging
import os
import schedule
import sys
import time
import tweettoot
import traceback

# Initialize common logging options
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

configs = []
with open("./config_files") as file:
    for line in file: 
        line = line.strip()
        configs.append(line)

every_x_minutes = helpers._config("TT_RUN_EVERY_X_MINUTES", "sysconfig.json")

def runJob():
    for config in configs:
        # Initialize variables
        app_name = helpers._config("TT_APP_NAME", config)
        twitter_url = helpers._config("TT_SOURCE_TWITTER_URL", config)
        mastodon_url = helpers._config("TT_HOST_INSTANCE", config)
        mastodon_token = helpers._config("TT_APP_SECURE_TOKEN", config)
        mastodon_client_id = helpers._config("TT_APP_CLIENT_ID", config)
        mastodon_client_token = helpers._config("TT_APP_CLIENT_TOKEN", config)
        twitter_user_id = helpers._config("TT_TWITTER_USER_ID", config)
        twitter_api_key = helpers._config("TT_TWITTER_CONSUMER_KEY", config)
        twitter_api_secret = helpers._config("TT_TWITTER_CONSUMER_SECRET", config)
        twitter_user_key = helpers._config("TT_TWITTER_TOKEN", config)
        twitter_user_secret = helpers._config("TT_TWITTER_TOKEN_SECRET", config)
        tweet_amount = helpers._config("TT_NUMBER_OF_TWEETS", config)
        strip_urls = False
        include_rts = False
        misskey = False

        if (helpers._config("TT_STRIP_URLS", config).lower() == "yes"):
            strip_urls = True

        if (helpers._config("TT_INCLUDE_RTS", config).lower() == "yes"):
            include_rts = True

        if (helpers._config("TT_MISSKEY", config).lower() == "yes"):
            misskey = True

        try:
            job = tweettoot.TweetToot(
                app_name = app_name,
                twitter_url = twitter_url,
                mastodon_url = mastodon_url,
                mastodon_token = mastodon_token,
                mastodon_client_id = mastodon_client_id,
                mastodon_client_token = mastodon_client_token,
                twitter_user_id = twitter_user_id,
                twitter_api_key = twitter_api_key,
                twitter_api_secret = twitter_api_secret,
                twitter_user_key = twitter_user_key,
                twitter_user_secret = twitter_user_secret,
                strip_urls = strip_urls,
                include_rts = include_rts,
                tweet_amount = tweet_amount,
                misskey = misskey
            )
            job.relay()
        except Exception as e:
            logger.critical(e)
            traceback.print_exc()

    return True

if __name__ == "__main__":
    runJob()
    schedule.every(every_x_minutes).minutes.do(runJob)

    while 1:
        schedule.run_pending()
        time.sleep(1)    
