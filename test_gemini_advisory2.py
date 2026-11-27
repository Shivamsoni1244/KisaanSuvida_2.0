import os, sys
from dotenv import load_dotenv
load_dotenv(r'C:\\Users\\shubh\\Desktop\\Kisaan Suvida 2.0\\.env', override=True)
sys.path.append(r'C:\\Users\\shubh\\Desktop\\Kisaan Suvida 2.0')
from services.disease_advisory_service import get_disease_advisory

advisory = get_disease_advisory(
    crop_name='Tomato',
    disease_name='Early_blight',
    scientific_name=None,
    confidence=0.85,
    language='en',
    symptoms='yellow spots',
    location='Punjab'
)
print('Advisory result:', advisory)
