import os, sys
from dotenv import load_dotenv
load_dotenv(r'C:\\Users\\shubh\\Desktop\\Kisaan Suvida 2.0\\.env', override=True)
sys.path.append(r'C:\\Users\\shubh\\Desktop\\Kisaan Suvida 2.0')

from services.disease_engine import preprocess_leaf_image, predict_disease, get_prediction_details
from services.disease_advisory_service import get_disease_advisory

# Path to the uploaded image the user provided
image_path = r'C:\\Users\\shubh\.gemini\antigravity\brain\166f59a0-a3b3-40f7-8a80-babcbc5d772a\.user_uploaded\media_1795783195512_bc718822.jpg'

with open(image_path, 'rb') as f:
    image_bytes = f.read()

# Convert bytes to a BytesIO object for the preprocess function
import io
image_array = preprocess_leaf_image(io.BytesIO(image_bytes))

prediction = predict_disease(image_array)
print('CNN prediction:', prediction)

prediction_details = get_prediction_details(prediction)
print('Prediction details:', prediction_details)

advisory = get_disease_advisory(
    crop_name=prediction_details['crop_name'],
    disease_name=prediction_details['disease_name'],
    scientific_name=None,
    confidence=prediction_details['confidence'],
    language='en',
    symptoms=None,
    location=None,
)
print('Advisory result:', advisory)
