from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates'))
t = env.get_template('crop_result.html')
print("Template compiles successfully")

html = t.render(
    result={
        'top_crop': {
            'name': 'Rice (Paddy)',
            'summary': 'A strong fit for Kharif season',
            'ml_probability': 92,
            'explanation': 'Rice thrives in alluvial soil with good irrigation during Kharif season.',
            'explanation_source': 'mistral_ai',
            'soil_compatibility': 96,
            'seasonal_compatibility': 98,
            'regional_compatibility': 89,
            'states_where_it_grows': ['Punjab', 'Haryana', 'Uttar Pradesh'],
            'did_you_know': 'Rice is grown in both irrigated and rain-fed systems.',
            'water_requirement': 'High',
            'weather_summary': '29°C • 72% humidity',
            'weather_advice': 'Maintain shallow standing water',
            'cultivation_risks': ['Pest pressure', 'Waterlogging']
        },
        'alternatives': [
            {'name': 'Maize', 'suitability_score': 84, 'summary': 'Alternative grain crop', 'water_requirement': 'Medium', 'season': 'Kharif'},
            {'name': 'Cotton', 'suitability_score': 82, 'summary': 'Cash crop option', 'water_requirement': 'Medium', 'season': 'Kharif'}
        ],
        'validation': {
            'validation_status': 'valid',
            'summary': 'Recommendation is suitable',
            'risks': ['Pest pressure']
        },
        'disclaimer': 'AI-generated results. Consult local agronomist.',
        'farm_context': {'district': 'Ludhiana', 'state': 'Punjab', 'season': 'Kharif', 'soil_type': 'Alluvial', 'irrigation': 'Canal irrigation'},
        'source': 'multi_llm',
        'ml_probability': 92
    },
    weather_display={
        'is_real_time': True,
        'temperature_display': '29°C',
        'humidity_display': '72%',
        'description': 'Partly cloudy',
        'rainfall_display': '8 mm rain'
    },
    current_greeting='Good Morning',
    current_user={'name': 'Rajesh Kumar'},
    current_date='21 Nov 2026',
    current_time='10:30 AM',
    active_page='recommendation'
)

html_str = str(html)
print('Template renders successfully')
print(f'HTML length: {len(html_str)} chars')
print()
print('Verification:')
print('  - Validation banner removed:', 'Agricultural Validation' not in html_str)
print('  - Validation section removed:', 'Contradictions Found' not in html_str and 'Additional Information Needed' not in html_str)
print(f'  - KisaanBot section present: {"Why is Rice (Paddy) a good fit?" in html_str}')
print(f'  - Ask KisaanBot button: {"Ask KisaanBot" in html_str}')
print(f'  - sendKisaanbotQuestion function: {"sendKisaanbotQuestion" in html_str}')
print(f'  - Explanation present: {"Rice thrives in alluvial soil" in html_str}')
