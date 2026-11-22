with open('routes/crop_routes.py', 'r') as f:
    lines = f.readlines()
print('Before fix:')
for i in range(132, 137):
    print(f'  Line {i+1}: {repr(lines[i])}')
lines[132] = '    auto_season = _get_automatic_season(\n'
lines[133] = '    state = user.get("state", "Punjab"),\n'
lines[134] = '    district = user.get("district", "Ludhiana"),\n'
lines[135] = '        )\n'
with open('routes/crop_routes.py', 'w') as f:
    f.writelines(lines)
print()
print('After fix:')
with open('routes/crop_routes.py', 'r') as f:
    lines = f.readlines()
    for i in range(132, 137):
        print(f'  Line {i+1}: {repr(lines[i])}')