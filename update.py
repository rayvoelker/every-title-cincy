import requests
import json
from uuid import uuid4
from time import sleep
import re
import imghdr
from string import capwords

# from IPython.display import Image
import tweepy

chpl_collection_url = (
    "https://ilsweb.cincinnatilibrary.org/collection-analysis/current_collection"
)

# read from the config
try:
    with open("./config.json", "r") as f:
        config = json.load(f)

    bc_key = config["bc_key"]
    access_token = config["twitter_creds"]["access_token"]
    access_token_secret = config["twitter_creds"]["access_token_secret"]
    consumer_key = config["twitter_creds"]["consumer_key"]
    consumer_secret = config["twitter_creds"]["consumer_secret"]

except:
    exit()

sql = """\
with bib_data as (
  with random_bib as (
    select
      :guid as query_guid,
      datetime('now', 'localtime') as time_stamp,
      bib.bib_record_num
    from
      bib
    where
      bib.publish_year is not null
      and bib.publish_year != ''
      and bib.publish_year >= 1830
      and bib.publish_year <= cast(strftime('%Y', 'now') as INTEGER)
      and bib.isbn is not null
    order by
      random()
    limit
      1
  )
  select
    r.query_guid,
    r.time_stamp,
    r.bib_record_num,
    count(
      case
        when item.item_status_code IN ('-', 'd', 't') then 1
        else 0
      end
    ) as count_available,
    count(item.item_record_num) as count_total_items,
    (
      sum(item.checkout_total) + sum(item.renewal_total)
    ) as sum_circulation,
    max(
      coalesce(
        item.last_checkin_date,
        item.checkout_date,
        item.last_checkout_date
      )
    ) as last_circ_date,
    -- ltrim(strftime('%m/%Y', last_circ_date), '0') as last_circ_month,
    -- max(item.item_format) as item_format,
    (
      select
        group_concat(item_format, ', ')
      from
        (
          select
            distinct item.item_format
          from
            item
          where
            bib_record_num = r.bib_record_num
            and item.item_status_code IN ('-', 'd', 't')
          order by
            item_format
        )
    ) as item_format,
    max(item.item_callnumber) as callnumber
  from
    random_bib as r -- join bib on bib.bib_record_num = r.bib_record_num
    join item on item.bib_record_num = r.bib_record_num
  group by
    1,
    2,
    3
  having
    count(
      case
        when item.item_status_code IN ('-', 'd', 't') then 1
        else 0
      end
    ) > 1
)
select
  d.query_guid,
  d.time_stamp,
  d.bib_record_num,
  d.count_available,
  d.count_total_items,
  d.sum_circulation,
  d.last_circ_date,
  ltrim(strftime('%m/%Y', d.last_circ_date), '0') as last_circ_month,
  d.item_format,
  callnumber,
  bib.*
from
  bib_data as d
  join bib on bib.bib_record_num = d.bib_record_num
"""

# Note: the random search may not return a value, so loop up to 100 times
# Note: we're sending a guid so that we can make sure the query is not being cached
count = 100
while count:
    count -= 1
    print(".", end="")

    try:
        r = requests.get(
            chpl_collection_url + ".json",
            params={"sql": sql, "_shape": "array", "guid": str(uuid4())},
        )
        if len(r.json()) > 0:
            break

        # df = pd.read_json(r.text)

    except:
        pass

    sleep(1)

print("\n", json.dumps(r.json(), indent=2), sep="")

try:
    r_open_library = requests.get(
        "https://covers.openlibrary.org/b/isbn/{}-L.jpg".format(r.json()[0]["isbn"])
    )
    if imghdr.what(None, h=r_open_library.content) == "jpeg":
        print(
            "https://covers.openlibrary.org/b/isbn/{}-L.jpg".format(r.json()[0]["isbn"])
        )
        # break
    else:
        print("No Image Found", end="")
except:
    pass

try:
    r_title = requests.get(
        url="https://api.bibliocommons.com/v1/titles/{}".format(
            str(r.json()[0]["bib_record_num"]) + "170"
        ),
        params={"api_key": bc_key},
    )

    print(r_title.json()["title"]["description"])
    # print(r_title.status_code, json.dumps(r_title.json(), indent=2), sep="\n")
except:
    pass

# Image(r_open_library.content)

# 280 characters max (includes a link, representing 23 characters ... see below)
# A URL of any length will be altered to 23 characters,
# even if the link itself is less than 23 characters long,
# character count will reflect this.
tweet = ""
tweet += """{}""".format(capwords(str(r.json()[0]["best_title"])))
if r.json()[0]["best_author"] is not None:
    tweet += """—{}\n""".format(str(r.json()[0]["best_author"]))
else:
    tweet += """\n"""

# regex to replace excess whitespace
re_compress_space = re.compile("\s+")

tweet += """{}
{} | {}
items: {} | circs: {}""".format(
    str(r.json()[0]["publish_year"]),
    str(r.json()[0]["item_format"]),
    re_compress_space.sub(" ", str(r.json()[0]["callnumber"])),
    str(r.json()[0]["count_available"]),
    str(r.json()[0]["sum_circulation"]),
)

if r.json()[0]["last_circ_month"] is not None:
    tweet += """ | last circ: {}\n""".format(r.json()[0]["last_circ_month"])
else:
    tweet += """\n"""

extra = ""
if r.json()[0]["indexed_subjects"] is not None:
    subject = re_compress_space.sub(" ", str(r.json()[0]["indexed_subjects"]))
    if len(subject) <= (253 - len(tweet)):
        extra += subject
        extra += "\n"
    else:
        extra += subject[: 253 - len(tweet)]
        extra += "... "

extra += """https://cincinnatilibrary.bibliocommons.com/v2/record/S170C{}""".format(
    str(r.json()[0]["bib_record_num"])
)

print(tweet + extra)
print(len(tweet + extra))

from tweepy import media

client = tweepy.Client(
    consumer_key=consumer_key,
    consumer_secret=consumer_secret,
    access_token=access_token,
    access_token_secret=access_token_secret,
)

response = client.create_tweet(
    text=tweet + extra,
    # media_ids=
)
print(f"https://twitter.com/user/status/{response.data['id']}")

img_link = ""
try:
    r_open_library = requests.get(
        "https://covers.openlibrary.org/b/isbn/{}-L.jpg".format(r.json()[0]["isbn"])
    )
    if imghdr.what(None, h=r_open_library.content) == "jpeg":
        print(
            "https://covers.openlibrary.org/b/isbn/{}-L.jpg".format(r.json()[0]["isbn"])
        )
        img_link = "https://covers.openlibrary.org/b/isbn/{}-L.jpg".format(
            r.json()[0]["isbn"]
        )
        # break
    else:
        print("No Image Found", end="")
except:
    pass

try:
    response2 = client.create_tweet(
        text=img_link + "\n" + r_title.json()["title"]["description"][:253],
        in_reply_to_tweet_id=response.data["id"]
        # media_ids=
    )
    print(f"https://twitter.com/user/status/{response2.data['id']}")
except:
    pass
