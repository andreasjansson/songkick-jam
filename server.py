import cPickle
import functools
from redis import StrictRedis
import collections
import datetime
import requests
import argparse
from flask import Flask, request, render_template

app = Flask(__name__)
redis = StrictRedis(host='localhost', port=6379)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', events_by_date={})

@app.route('/results', methods=['GET'])
def results():
    username = request.args['username']
    location = request.args['location']
    page = request.args.get('page')
    if page:
        page = int(page)
    try:
        shows, done = fetch_shows(username, location, page=page)
        error = None
    except JamSongkickException as e:
        shows = []
        error = e.message

    template = 'index.html' if page is None else 'results.html'
    return render_template(template, username=username, location=location,
                           events_by_date=shows, error=error, done=done)

def cached(key_format, ttl=None):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args):
            key = key_format % args
            resp = redis.get(key)
            if resp:
                return cPickle.loads(resp)
            ret = f(*args)
            redis.set(key, cPickle.dumps(ret))
            if ttl:
                redis.expire(key, ttl)
            return ret

        return wrapper
    return decorator

def fetch_shows(username, location, page=None):
    jams = fetch_jams(username)
    likes = fetch_likes(username)
    location_id = fetch_location(location)
    events, done = fetch_events(jams + likes, location_id, page=page)
    return events_by_date(events), done

def events_by_date(unordered):
    events = collections.OrderedDict()
    for event in sorted(unordered, key=lambda e: e['start']['datetime']):
        date = event['start']['date']
        if date not in events:
            events[date] = []
        events[date].append(event)
    return events

@cached('location:%s')
def fetch_location(location):
    locations = songkick_search('locations.json', query=location)['location']
    if not locations:
        raise JamSongkickException('"%s" is not a known location!' % location)

    return locations[0]['metroArea']['id']

def fetch_events(jams, location_id, page=None, per_page=10):
    events = []
    artists = sorted([a for a in set([j['artist'] for j in jams]) if a])
    if page is None:
        done = True
    else:
        done = page * per_page >= len(artists)
        artists = artists[:page * per_page]


    now = datetime.datetime.now()
    three_months = datetime.timedelta(days=90)
    max_date = (now + three_months).strftime('%Y-%m-%d')
    for artist in artists:
        events += fetch_artist_events(artist, location_id, max_date)

    return events, done

@cached('artist_events:%s:%s:%s', 60 * 60 * 24 * 7)
def fetch_artist_events(artist, location_id, max_date):
    return songkick_search('events.json',
                           artist_name=artist,
                           location='sk:%s' % location_id,
                           max_date=max_date)['event']

def songkick_search(endpoint, **kwargs):

    if endpoint == 'locations.json':
        resp = dummy_location_search_response
    if endpoint == 'events.json':
        resp = dummy_event_search_response


#    url = 'http://api.songkick.com/api/3.0/%s' % endpoint
#    params = {'apikey': app.config['song_kick_api_key'], 'per_page': 50}
#    params.update(kwargs)
#    r = requests.get(url, params=params)
#    resp = r.json()
    return resp['resultsPage']['results']

@cached('jams:%s', 60 * 60 * 24 * 7)
def fetch_jams(username):
    return paginate_jams('%s/jams.json' % username)

@cached('likes:%s', 60 * 60 * 24 * 7)
def fetch_likes(username):
    return paginate_jams('%s/likes.json' % username)

def paginate_jams(endpoint):
    url = 'http://api.thisismyjam.com/1/%s' % endpoint
    has_more = True
    page = 1
    data = []
    while has_more:
        r = requests.get(url, params={'page': page, 'key': app.config['jam_api_key']})
        if r.status_code == 404:
            raise JamSongkickException('Not a valid This Is My Jam username')

        resp = r.json()
        has_more = resp['list']['hasMore']
        data += resp['jams']
        page += 1

    return data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--song-kick-api-key')
    parser.add_argument('-j', '--jam-api-key')
    parser.add_argument('-d', '--debug', action='store_true')
    args = parser.parse_args()
    app.config['song_kick_api_key'] = args.song_kick_api_key
    app.config['jam_api_key'] = args.jam_api_key

    app.run(debug=args.debug)

class JamSongkickException(Exception): pass

dummy_event_search_response = \
{
      "resultsPage": {
          "page": 1,
          "totalEntries": 2,
          "perPage": 50,
          "results": {
              "event": [{
                  "displayName": "Vampire Weekend at O2 Academy Brixton (February 16, 2010)",
                  "type": "Concert",
                  "uri": "http://www.songkick.com/concerts/3037536-vampire-weekend-at-o2-academy-brixton?utm_medium=partner&utm_source=PARTNER_ID",
                  "venue": {
                      "lng": -0.1187418,
                      "displayName": "O2 Academy Brixton",
                      "lat": 51.4681089,
                      "id": 17522,
                  },
                  "location": {
                      "lng": -0.1187418,
                      "city": "London, UK",
                      "lat": 51.4681089
                  },
                  "start": {
                      "time": "19:30:00",
                      "date": "2010-02-16",
                      "datetime": "2010-02-16T19:30:00+0000"
                  },
                  "performance": [{
                      "artist": {
                          "uri": "http://www.songkick.com/artists/288696-vampire-weekend",
                          "displayName": "Vampire Weekend",
                          "id": 288696,
                          "identifier": [{"mbid": "af37c51c-0790-4a29-b995-456f98a6b8c9"}]
                      },
                     "displayName": "Vampire Weekend",
                     "billingIndex": 1,
                     "id": 5380281,
                     "billing": "headline"
                  }],
                  "id": 3037536
              },
              {
                  "displayName": "Vampire Weekend at O2 Academy Brixton (February 17, 2010)",
                  "type": "Concert",
                  "uri": "http://www.songkick.com/concerts/3078766-vampire-weekend-at-o2-academy-brixton?utm_medium=partner&utm_source=PARTNER_ID",
                  "venue": {
                      "lng": -0.1187418,
                      "displayName": "O2 Academy Brixton",
                      "lat": 51.4681089,
                      "id": 17522,
                  },
                  "location": {
                      "lng": -0.1187418,
                      "city": "London, UK",
                      "lat": 51.4681089
                  },
                  "start": {
                      "time": "19:30:00",
                      "date": "2010-02-17",
                      "datetime": "2010-02-17T19:30:00+0000"
                  },
                  "performance": [{
                      "artist": {
                          "uri": "http://www.songkick.com/artists/288696-vampire-weekend",
                          "displayName": "Vampire Weekend",
                          "id": 288696,
                          "identifier": [{"mbid": "af37c51c-0790-4a29-b995-456f98a6b8c9"}]
                      },
                      "displayName": "Vampire Weekend",
                      "billingIndex": 1,
                      "id": 5468321,
                      "billing": "headline"
                  }],
                  "id": 3078766
              }]
          }
      }
  }


dummy_location_search_response = \
{"resultsPage":
    {"results":
      {"location":[{
        "city":{"displayName":"London",
                "country":{"displayName":"UK"},
                "lng":-0.128,"lat":51.5078},
        "metroArea":{"uri":"http://www.songkick.com/metro_areas/24426-uk-london",
                     "displayName":"London",
                     "country":{"displayName":"UK"},
                     "id":24426,
                     "lng":-0.128,"lat":51.5078}},
        {"city":{"displayName":"London",
                 "country":{"displayName":"US"},
                 "lng":None,"lat":None,
                 "state":{"displayName":"KY"}},
        "metroArea":{"uri":"http://www.songkick.com/metro_areas/24580",
                     "displayName":"Lexington",
                     "country":{"displayName":"US"},
                     "id":24580,
                     "lng":-84.4947,"lat":38.0297,
                     "state":{"displayName":"KY"}}}
    ]},
    "totalEntries":2,"perPage":10,"page":1,"status":"ok"}}



if __name__ == '__main__':
    main()


