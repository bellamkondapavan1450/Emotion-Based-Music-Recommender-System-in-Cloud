from google.cloud import storage
import pandas as pd
import requests
import datetime
import base64
import pickle
from sklearn.preprocessing import MinMaxScaler


client_id = '856fb9c36fd14dd7ab5569a881da1219'
client_secret = '5293c698c4444ff2824d596bf985f222'
storage_client = storage.Client()
bucket = storage_client.get_bucket('sample-storage-123')


class SpotifyAPI(object):
    access_token = None
    access_token_expires = datetime.datetime.now()
    access_token_did_expire = True
    client_id = None
    client_secret = None
    token_url = "https://accounts.spotify.com/api/token"
    
    def __init__(self, client_id, client_secret):
        super().__init__()
        self.client_id = client_id
        self.client_secret = client_secret

    def get_client_credentials(self):
        """
        Returns a base64 encoded string
        """
        client_id = self.client_id
        client_secret = self.client_secret
        if client_secret == None or client_id == None:
            raise Exception("You must set client_id and client_secret")
        client_creds = f"{client_id}:{client_secret}"
        client_creds_b64 = base64.b64encode(client_creds.encode())
        return client_creds_b64.decode()
    
    def get_token_headers(self):
        client_creds_b64 = self.get_client_credentials()
        return {
            "Authorization": f"Basic {client_creds_b64}"
        }
    
    def get_token_data(self):
        return {
            "grant_type": "client_credentials"
        } 
    
    def perform_auth(self):
        token_url = self.token_url
        token_data = self.get_token_data()
        token_headers = self.get_token_headers()
        r = requests.post(token_url, data=token_data, headers=token_headers)
        if r.status_code not in range(200, 299):
            raise Exception("Could not authenticate client.")
            # return False
        data = r.json()
        now = datetime.datetime.now()
        access_token = data['access_token']
        expires_in = data['expires_in'] # seconds
        expires = now + datetime.timedelta(seconds=expires_in)
        self.access_token = access_token
        self.access_token_expires = expires
        self.access_token_did_expire = expires < now
        return True
    
    def get_access_token(self):
        token = self.access_token
        expires = self.access_token_expires
        now = datetime.datetime.now()
        if expires < now:
            self.perform_auth()
            return self.get_access_token()
        elif token == None:
            self.perform_auth()
            return self.get_access_token() 
        return token
    
    def get_resource_header(self):
        access_token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        return headers
    
    
    def get_playlist(self, playlist_id):
        access_token = self.get_access_token()
        endpoint = f"https://api.spotify.com/v1/playlists/{playlist_id}"
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        r = requests.get(endpoint, headers=headers)
        if r.status_code not in range(200, 299):
            return {}
        return r.json()


    def get_audio_features(self, track_id):
        access_token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        endpoint = f'https://api.spotify.com/v1/audio-features/{track_id}'
        r = requests.get(endpoint, headers=headers)
        if r.status_code not in range(200, 299):
            return {}
        return r.json()
    


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



def classify_songs(event, context):
    playlist_id = base64.b64decode(event['data']).decode('utf-8')
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
    spotify = SpotifyAPI(client_id, client_secret)
    r = spotify.get_playlist(playlist_id)
    if(r):
        tracks = r['tracks']['items']
        for song in tracks:
            track_id = song['track']['id']
            res = spotify.get_audio_features(track_id=track_id)
            if(res):
                track_uri.append(res['uri'])
                acousticness.append(res['acousticness'])
                danceability.append(res['danceability'])
                energy.append(res['energy'])
                instrumentalness.append(res['instrumentalness'])
                liveness.append(res['liveness'])
                loudness.append(res['loudness'])
                speechiness.append(res['speechiness'])
                tempo.append(res['tempo'])
                valence.append(res['valence'])
    print("Songs Features Extracted...")
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
    model.download_to_filename('/tmp/model.pkl')
    pkl_model = pickle.load(open('/tmp/model.pkl', 'rb'))
    clist = ["danceability", "acousticness", "energy", "instrumentalness", "liveness", "valence", "loudness", "speechiness", "tempo"]
    x = df[clist]
    print("Preprocessing Data...")
    scaler = MinMaxScaler()
    x = preprocess_data(x, scaler)
    print("Classifying Songs...")
    y = pkl_model.predict(x)
    df['mood'] = y
    df.to_csv('/tmp/songs_features.csv')
    blob = bucket.blob('songs_features.csv')
    blob.upload_from_filename('/tmp/songs_features.csv')
    print("Songs Classification done and saved to the storage bucket...")
    return True