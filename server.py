import os
import cPickle
import functools
from redis import StrictRedis
import collections
import datetime
import requests
import urllib
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
        shows = {}
        error = e.message
        done = True

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
            print 'uncached %s' % key
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
    events = events_with_jams(events, jams + likes)
    return events_by_date(events), done

def fuzzy(s):
    return s.lower().replace(' ', '')

def events_with_jams(events, jams):
    jams_by_artist = {}
    for jam in jams:
        artist = fuzzy(jam['artist'])

        if artist not in jams_by_artist:
            via_url = jam.get('viaUrl')
            if via_url and ('youtube' in via_url
                            or 'vimeo' in via_url
                            or 'soundcloud' in via_url
                            or 'bandcamp' in via_url):
                jam['url'] = via_url
            else:
                search_query = urllib.quote_plus(('%s - %s' % (jam['artist'], jam['title'])).encode('utf8'))
                jam['url'] = 'https://www.youtube.com/results?search_query=%s' % search_query

            jams_by_artist[artist] = jam

    for e in events:
        artist = e['performance'][0]['artist']['displayName']
        e['jam'] = jams_by_artist.get(fuzzy(artist))

    return events

def events_by_date(unordered):
    events = collections.OrderedDict()
    for event in sorted(unordered, key=lambda e: '%s%s' % (e['start']['date'], e['start']['datetime'])):
        date = event['start']['date']
        if date not in events:
            events[date] = []
        events[date].append(event)
    return events

@cached('location:%s')
def fetch_location(location):
    locations = songkick_search('search/locations.json', query=location)['location']
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
    three_months = datetime.timedelta(days=120)
    max_date = (now + three_months).strftime('%Y-%m-01')
    today = now.strftime('%Y-%m-%d')
    for artist in artists:
        artist_events = fetch_artist_events(artist, location_id, max_date)
        future_events = [e for e in artist_events if e['start']['date'] >= today]
        events += future_events

    return events, done

@cached('artist_events:%s:%s:%s', 60 * 60 * 24 * 7)
def fetch_artist_events(artist, location_id, max_date):
    min_date = datetime.datetime.now().strftime('%Y-%m-01')
    return songkick_search('events.json',
                           artist_name=artist,
                           location='sk:%s' % location_id,
                           min_date=min_date,
                           max_date=max_date).get('event', [])

def songkick_search(endpoint, **kwargs):
    url = 'http://api.songkick.com/api/3.0/%s' % endpoint
    params = {'apikey': app.config['song_kick_api_key'], 'per_page': 50}
    params.update(kwargs)
    r = requests.get(url, params=params)
    resp = r.json()
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
    app.config['song_kick_api_key'] = os.environ['SONG_KICK_API_KEY']
    app.config['jam_api_key'] = os.environ['JAM_API_KEY']

    app.run(debug=True, host='0.0.0.0')

class JamSongkickException(Exception): pass


if __name__ == '__main__':
    main()


