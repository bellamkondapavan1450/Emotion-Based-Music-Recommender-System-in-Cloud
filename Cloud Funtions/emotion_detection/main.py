from tensorflow import keras
import cv2
import numpy as np
from google.cloud import storage
import random 

classes = ["happy", "sad"]

storage_client = storage.Client()
bucket1 = storage_client.get_bucket('sample-storage-123')
bucket2 = storage_client.get_bucket('sample-client-123')

def predict_emotion(event, context):

    model = bucket1.blob('cnnModel.h5')
    model.download_to_filename('/tmp/cnnModel.h5')
    emot_model = keras.models.load_model('/tmp/cnnModel.h5')
    print("Model Loaded...")
    
    filename = [filename.name for filename in list(bucket2.list_blobs(prefix=''))]
    while(event['name'] not in filename):
        print('Waiting for Image Upload...')
        filename = [filename.name for filename in list(bucket2.list_blobs(prefix=''))]
    picture = bucket2.blob(event['name'])
    picture.download_to_filename('/tmp/person.jpg')
    print("Image Loaded...")

    xml = bucket1.blob('haarcascade_frontalface_default.xml')
    xml.download_to_filename('/tmp/haarcascade_frontalface_default.xml')
    print("xml File loaded...")

    picture = cv2.imread('/tmp/person.jpg')
    faceCascade = cv2.CascadeClassifier("/tmp/haarcascade_frontalface_default.xml")
    g = cv2.cvtColor(picture, cv2.COLOR_BGR2GRAY)
    faces = faceCascade.detectMultiScale(g, scaleFactor=1.2, minNeighbors=4)

    if(len(faces) == 1):
        print('Face detected...')
        for (x, y, w, h) in faces:
            picture = picture[y:y+h, x:x+w]
        gray = cv2.cvtColor(picture, cv2.COLOR_BGR2GRAY)
        face = cv2.resize(gray, (48, 48))
        face = np.array(face)
        final_face = face/255.0
        final_face = np.array(final_face).reshape(-1, 48, 48, 1)
        prediction = emot_model.predict(final_face)
        print("Predictions of all class : {}".format(prediction[0]))
        print("\nMax Value is at {} position.".format(np.argmax(prediction)))
        print("\nBelongs to {} class.".format(classes[np.argmax(prediction)]))
        blob = bucket1.blob('emotion.txt')
        blob.upload_from_string(classes[np.argmax(prediction)])
        print("Emotion written to the emotion.txt")
        bucket2.delete_blob(event['name'])
        print("Image Deleted from the Bucket...")

    else:
        print("Face not found or multiple faces detected...")
        i = random.randint(0, 2)
        blob = bucket1.blob('emotion.txt')
        print("Random Emotion written to the emotion.txt")
        blob.upload_from_string(classes[i])

    return f"done"