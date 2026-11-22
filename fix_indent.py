with open('routes/crop_routes.py', 'r') as f:
    lines = f.readlines()
lines[131] = '        # Determine automatic season\n'
lines[132] = '        auto_season = _get_automatic_season(\n'
lines[133] = '            user.get("state", "Punjab"),\n'
lines[134] = '            user.get("district", "Ludhiana"),\n'
lines[135] = '        )\n'
with open('routes/crop_routes.py', 'w') as f:
    f.writelines(lines)
print('Fixed indentation at lines 132-136')