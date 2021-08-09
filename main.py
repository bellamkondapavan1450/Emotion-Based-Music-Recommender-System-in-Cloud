from flask import Flask, render_template, url_for, session, request, redirect
import base64
import pandas as pd
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time
from google.cloud import storage
from google.cloud import pubsub_v1
import os
import json
import pickle
from sklearn.preprocessing import MinMaxScaler


PATH = os.path.join(os.getcwd(), 'static\\json\\thesis-project-2021-f018d364eb67.json')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = PATH

client_id = '856fb9c36fd14dd7ab5569a881da1219'
client_secret = '5293c698c4444ff2824d596bf985f222'
username = ''
emot = ''
playlist_id = ''
filename = ''


app = Flask(__name__)

app.secret_key = 'bellamkondapavan1450'
app.config['SESSION_COOKIE_NAME'] = 'spotify-login-session'


@app.route('/')
@app.route('/home')
def home():
    return render_template('home.html')


@app.route('/login')
def login():
    sp_oauth = create_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    print(auth_url)
    return redirect(auth_url)


@app.route('/authorize')
def authorize():
    sp_oauth = create_spotify_oauth()
    session.clear()
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session["token_info"] = token_info
    return redirect("/application")


@app.route('/application')
def application():
    session['token_info'], authorized = get_token()
    session.modified = True
    if not authorized:
        return redirect('/login')
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    res = sp.current_user()
    print(json.dumps(res, indent=4, sort_keys=True))
    global username
    username = res['id']
    global filename
    filename = username+'.jpg'
    print(filename)
    return render_template('application.html', name=res['display_name'])


@app.route('/application/data', methods=['POST'])
def application_data():
    req = request.get_json()
    image_uri = req['uri']
    image = image_uri.replace('data:image/jpeg;base64,', '')
    with open("static/images/person.jpg", "wb") as f:
        f.write(base64.urlsafe_b64decode(image))
    print("Image Captured Successfully...")
    # upload image in Cloud Storage and perform Emotion classification
    storage_client = storage.Client(PATH)
    bucket = storage_client.get_bucket('sample-client-123')
    picture = bucket.blob(filename)
    picture.upload_from_filename('static\images\person.jpg')
    print('Done Uploading Captured Image to the client bucket...')
    # cloud function triggers and emotion will be saved to emotion .txt
    return req


@app.route('/dashboard')
def dashboard():
    session['token_info'], authorized = get_token()
    session.modified = True
    if not authorized:
        return redirect('/login')
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    r1 = sp.playlist('37i9dQZF1DX0XUfTFmNBRM')
    r2 = sp.playlist('37i9dQZF1DX1i3hvzHpcQV')
    r3 = sp.playlist('37i9dQZF1DX6XE7HRLM75P')
    r4 = sp.playlist('37i9dQZF1DWXVJK4aT7pmk')
    data = [
        {
            "id":r1["id"],
            "name":r1["name"],
            "uri":r1["images"][0]["url"]
        },
        {
            "id":r2["id"],
            "name":r2["name"],
            "uri":r2["images"][0]["url"]
        },
        {
            "id":r3["id"],
            "name":r3["name"],
            "uri":r3["images"][0]["url"]
        },
        {
            "id":r4["id"],
            "name":r4["name"],
            "uri":r4["images"][0]["url"]
        }]
    return render_template('dashboard.html', data=data)


@app.route('/dashboard/data', methods=['POST'])
def dashboard_data():
    req = request.get_json()
    global playlist_id
    playlist_id = req["id"]

    if(playlist_id != 'recentlyplayed'):
        # Publish playlist_id to PubSub
        publisher = pubsub_v1.PublisherClient()
        topic_path = 'projects/thesis-project-2021/topics/playlist-id'
        data = playlist_id.encode('utf-8')
        future = publisher.publish(topic_path, data)
        print('Playlist_ID published Successfully...')
        print(f'Published Message id {future.result()}')
        # cloud function triggers and Songs Classification will be done.
    return req


@app.route('/playlist')
def playlist():

    session['token_info'], authorized = get_token()
    session.modified = True
    if not authorized:
        return redirect('/login')
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))

    storage_client = storage.Client(PATH)
    bucket = storage_client.get_bucket('sample-storage-123')
    filename = [filename.name for filename in list(bucket.list_blobs(prefix='')) ]
    while ('emotion.txt' not in filename):
        print('Please wait. Emotion to be detected...')
        time.sleep(1)
        filename = [filename.name for filename in list(bucket.list_blobs(prefix=''))]
    emotion = bucket.blob('emotion.txt')
    global emot
    emot = emotion.download_as_text()
    print(emot)
    bucket.delete_blob('emotion.txt')
    
    if(playlist_id != 'recentlyplayed'):
        while ('songs_features.csv' not in filename):
            print('Please wait. Songs to be Classified...')
            time.sleep(2)
            filename = [filename.name for filename in list(bucket.list_blobs(prefix=''))]
        data = bucket.blob('songs_features.csv')
        data.download_to_filename('static/songs_features.csv')
        bucket.delete_blob('songs_features.csv')
        d = pd.read_csv('static/songs_features.csv')
        d1 = d[d['mood']==emot]
        tracks_uris = d1['uri'].tolist()
    else:
        track_ids = []
        track_uri = []
        acousticness = []
        danceability = []
        energy = []
        instrumentalness = []
        liveness = []
        loudness = []
        speechiness = []
        tempo = []
        valence = []
        r = sp.current_user_recently_played(limit=50)
        # print(json.dumps(r, indent=4, sort_keys=True))
        if(r):
            tracks = r['items']
            for song in tracks:
                track_id = song['track']['id']
                if(track_id not in track_ids):
                    track_ids.append(track_id)
                    res = sp.audio_features(track_id)
                    # print(json.dumps(res, indent=4, sort_keys=True))
                    if(res):
                        track_uri.append(res[0]['uri'])
                        acousticness.append(res[0]['acousticness'])
                        danceability.append(res[0]['danceability'])
                        energy.append(res[0]['energy'])
                        instrumentalness.append(res[0]['instrumentalness'])
                        liveness.append(res[0]['liveness'])
                        loudness.append(res[0]['loudness'])
                        speechiness.append(res[0]['speechiness'])
                        tempo.append(res[0]['tempo'])
                        valence.append(res[0]['valence'])
        df = pd.DataFrame()
        df['uri'] = track_uri
        df['acousticness'] = acousticness
        df['danceability'] = danceability
        df['energy'] = energy
        df['instrumentalness'] = instrumentalness
        df['liveness'] = liveness
        df['loudness'] = loudness
        df['speechiness'] = speechiness
        df['tempo'] = tempo
        df['valence'] = valence
        model = bucket.blob('model.pkl')
        model.download_to_filename('static/model.pkl')
        pkl_model = pickle.load(open('static/model.pkl', 'rb'))
        clist = ["danceability", "acousticness", "energy", "instrumentalness", "liveness", "valence", "loudness", "speechiness", "tempo"]
        x = df[clist]
        scaler = MinMaxScaler()
        x = preprocess_data(x, scaler)
        y = pkl_model.predict(x)
        df['mood'] = y
        df1 = df[df['mood']==emot]
        tracks_uris = df1['uri'].tolist()
    playlist_name = f'{emot} mood songs'.upper()
    sp.user_playlist_create(user=username, name=playlist_name, public=True, description='Music according to the mood')
    playlists = sp.user_playlists(username)
    sp.user_playlist_add_tracks(user=username, playlist_id=playlists['items'][0]['id'], tracks=tracks_uris)
    return render_template('playlist.html', id=playlists['items'][0]['id'])


@app.route('/loading')
def loading_data():
    return render_template('loading.html')


def create_spotify_oauth():
    return SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=url_for('authorize', _external=True),
            scope="user-read-email,playlist-modify-public,user-read-recently-played")


def get_token():
    token_valid = False
    token_info = session.get("token_info", {})
    if not (session.get('token_info', False)):
        token_valid = False
        return token_info, token_valid
    now = int(time.time())
    is_token_expired = session.get('token_info').get('expires_at') - now < 60
    if (is_token_expired):
        sp_oauth = create_spotify_oauth()
        token_info = sp_oauth.refresh_access_token(session.get('token_info').get('refresh_token'))
    token_valid = True
    return token_info, token_valid


def preprocess_data(data, scaler):
    
    new_data = data.copy()
    scaler.fit(data[["danceability"]])
    new_data[["danceability"]] = scaler.transform(data[["danceability"]])
    scaler.fit(data[["acousticness"]])
    new_data[["acousticness"]] = scaler.transform(data[["acousticness"]])
    scaler.fit(data[["energy"]])
    new_data[["energy"]] = scaler.transform(data[["energy"]])
    scaler.fit(data[["instrumentalness"]])
    new_data[["instrumentalness"]] = scaler.transform(data[["instrumentalness"]])
    scaler.fit(data[["liveness"]])
    new_data[["liveness"]] = scaler.transform(data[["liveness"]])
    scaler.fit(data[["valence"]])
    new_data[["valence"]] = scaler.transform(data[["valence"]])
    scaler.fit(data[["loudness"]])
    new_data[["loudness"]] = scaler.transform(data[["loudness"]])
    scaler.fit(data[["speechiness"]])
    new_data[["speechiness"]] = scaler.transform(data[["speechiness"]])
    scaler.fit(data[["tempo"]])
    new_data[["tempo"]] = scaler.transform(data[["tempo"]])
    
    return new_data