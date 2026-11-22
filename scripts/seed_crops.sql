-- Seed data for crop_recommendation engine
-- Run: mysql -u kisaan_user -pshubh1244 kisaan_suvidha < scripts/seed_crops.sql

-- First, ensure we have crop categories
INSERT IGNORE INTO crop_categories (name, description, is_active) VALUES
    ('Cereals', 'Cereal crops like rice, wheat, maize', 1),
    ('Pulses', 'Pulses and legumes like gram, chickpea', 1),
    ('Cash Crops', 'Cash crops like cotton, sugarcane', 1),
    ('Vegetables', 'Vegetable crops', 1),
    ('Fruits', 'Fruit crops', 1);

-- Insert crops
INSERT INTO crops (
    name, hindi_name, scientific_name, season,
    soils,
    n_range_min, n_range_max,
    p_range_min, p_range_max,
    k_range_min, k_range_max,
    ph_range_min, ph_range_max,
    soil_compatibility,
    season_compatibility,
    regional_compatibility,
    irrigation_compatibility,
    description, weather_summary, irrigation_advice,
    soil_desc, season_desc, region_desc,
    base_ml_prob, base_hybrid
) VALUES (
    'Rice (Paddy)', 'धान (चावल)', 'Oryza sativa', 'Kharif',
    '["Alluvial", "Clayey", "Black"]',
    70, 115, 40, 60, 30, 60, 6.5, 7.5,
    96, 98, 89, 95,
    'A strong fit for your farm this Kharif season.',
    '29°C • 72% humidity • 8 mm rain today',
    'Maintain shallow standing water after establishment. Adjust irrigation to rainfall and local agricultural guidance.',
    'Alluvial soil and pH 6.5 support healthy rice growth.',
    'Kharif warmth and monsoon moisture suit paddy cultivation.',
    'Punjab, Haryana, Uttar Pradesh, West Bengal, Andhra Pradesh, Telangana, Odisha, Chhattisgarh, Tamil Nadu, Bihar, Assam',
    92, 94
),
...
```

AH HA! I see it now! The seed_crops.sql file DOES have `soil_compatibility` column in the INSERT statement:

```sql
INSERT INTO crops (
    name, hindi_name, scientific_name, season,
    soils,
    n_range_min, n_range_max,
    p_range_min, p_range_max,
    k_range_min, k_range_max,
    ph_range_min, ph_range_max,
    soil_compatibility,
    season_compatibility,
    regional_compatibility,
    irrigation_compatibility,
    description, weather_summary, irrigation_advice,
    soil_desc, season_desc, region_desc,
    base_ml_prob, base_hybrid
) VALUES (
    'Rice (Paddy)', 'धान (चावल)', 'Oryza sativa', 'Kharif',
    '["Alluvial", "Clayey", "Black"]',
    70, 115, 40, 60, 30, 60, 30, 60, 6.5, 7.5,
    96, 98, 89, 95,
    ...
```

But looking at the migration file `003_create_crop_suitability_tables.sql`:
```sql
CREATE TABLE IF NOT EXISTS crops (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    scientific_name VARCHAR(100),
    hindi_name VARCHAR(100),
    season ENUM('Kharif', 'Rabi', 'Zaid', 'Perennial') NOT NULL,
    soils JSON,
    n_range_min DECIMAL(5,1),
    n_range_max DECIMAL(5,1),
    p_range_min DECIMAL(5,1),
    p_range_max DECIMAL(5,1),
    k_range_min DECIMAL(5,1),
    k_range_max DECIMAL(5,1),
    ph_range_min DECIMAL(3,1),
    ph_range_max DECIMAL(3,1),
    water_req ENUM('Low', 'Medium', 'High') NOT NULL DEFAULT 'Medium',
    water_requirement_mm DECIMAL(10,2)	YES		NULL	
    waterlog_tolerance	enum('Low','Medium','High')	NO		Medium	
    drought_tolerance	enum('Low','Medium','High')	NO		Medium	
    temp_min	decimal(5,1)	YES		NULL	
    temp_max	decimal(5,1)	YES		NULL	
    temp_optimal_min	decimal(5,1)	YES		NULL	
    temp_optimal_max	decimal(5,1)	YES		NULL	
    frost_tolerance	enum('Low','Medium','High')	NO		Medium	
    heat_tolerance	enum('Low','Medium','High')	NO		Medium	
    wind_tolerance	enum('Low','Medium','High')	NO		Medium	
    crop_duration_days	int	YES		NULL	
    sowing_start_month	int	YES		NULL	
    sowing_end_month	int	YES		NULL	
    harvesting_start_month	int	YES		NULL	
    harvesting_end_month	int	YES		NULL	
    description	text	YES		NULL	
    region_desc	text	YES		NULL	
    source_url	text	YES		NULL	
    source_name	varchar(255)	YES		NULL	
    created_at	timestamp	NO		CURRENT_TIMESTAMP	DEFAULT_GENERATED
    updated_at	timestamp	NO		CURRENT_TIMESTAMP	DEFAULT_GENERATED on update CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES crop_categories(id) ON DELETE CASCADE,
    INDEX idx_crops_name (name),
    INDEX idx_crops_category (category_id),
    INDEX idx_crops_season (season)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

WAIT! Looking at this migration file, I see:
- `soil_compatibility` column is MISSING!
- `season_compatibility` column is MISSING!
- `regional_compatibility` column is MISSING!
- `irrigation_compatibility` column is MISSING!

But the migration DOES have `water_req`, `water_requirement_mm`, etc.

Wait - I'm confused. Earlier I ran `Get-Content 'migrations/003_create_crop_suitability_tables.sql' | mysql -u kisaan_user -pshubh1244 kisaan_suvidha` and it said "Crop suitability tables migration applied." But looking at the migration content, it does NOT include `soil_compatibility`, `season_compatibility`, `regional_compatibility`, `irrigation_compatibility` columns!

So either:
1. The migration file I'm looking at now is different from what I ran earlier
2. Or the seed_crops.sql file expects columns that don't exist

Let me check what the migration file ACTUALLY contains again...

Looking at the migration file content I read earlier:
```
-- 2. Crops master table with full agronomic parameters
CREATE TABLE IF NOT EXISTS crops (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    scientific_name VARCHAR(100),
    hindi_name VARCHAR(100),
    season ENUM('Kharif', 'Rabi', 'Zaid', 'Perennial') NOT NULL,
    soils JSON,
    n_range_min DECIMAL(5,1),
    n_range_max DECIMAL(5,1),
    p_range_min DECIMAL(5,1),
    p_range_max DECIMAL(5,1),
    k_range_min DECIMAL(5,1),
    k_range_max DECIMAL(5,1),
    ph_range_min DECIMAL(3,1),
    ph_range_max DECIMAL(3,1),
    water_req ENUM('Low', 'Medium', 'High') NOT NULL DEFAULT 'Medium',
    water_requirement_mm DECIMAL(10,2)	YES		NULL	
    waterlog_tolerance	enum('Low','Medium','High')	NO		Medium	
    drought_tolerance	enum('Low','Medium','High')	NO		Medium	
    temp_min	decimal(5,1)	YES		NULL	
    temp_max	decimal(5,1)	YES		NULL	
    temp_optimal_min	decimal(5,1)	YES		NULL	
    temp_optimal_max	decimal(5,1)	YES		NULL	
    frost_tolerance	enum('Low','Medium','High')	NO		Medium	
    heat_tolerance	enum('Low','Medium','High')	NO		Medium	
    wind_tolerance	enum('Low','Medium','High')	NO		Medium	
    crop_duration_days	int	YES		NULL	
    sowing_start_month	int	YES		NULL	
    sowing_end_month	int	YES		NULL	
    harvesting_start_month	int	YES		NULL	
    harvesting_end_month	int	YES		NULL	
    description	text	YES		NULL	
    region_desc	text	YES		NULL	
    source_url	text	YES		NULL	
    source_name	varchar(255)	YES		NULL	
    created_at	timestamp	NO		CURRENT_TIMESTAMP	DEFAULT_GENERATED
    updated_at	timestamp	NO		CURRENT_TIMESTAMP	DEFAULT_GENERATED on update CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES crop_categories(id) ON DELETE CASCADE,
    INDEX idx_crops_name (name),
    INDEX idx_crops_category (category_id),
    INDEX idx_crops_season (season)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

I see it now! The migration file does NOT have `soil_compatibility`, `season_compatibility`, `regional_compatibility`, `irrigation_compatibility` columns! It only has `water_req`, `water_requirement_mm`, `waterlog_tolerance`, etc.

But `seed_crops.sql` tries to insert into `soil_compatibility`, `season_compatibility`, `regional_compatibility`, `irrigation_compatibility` columns that DON'T EXIST yet!

So I need to:
1. Add these columns to the `crops` table
2. Then run the seed script again

Let me add the missing columns:

```sql
ALTER TABLE crops ADD COLUMN soil_compatibility INT DEFAULT 0;
ALTER TABLE crops ADD COLUMN season_compatibility INT NOT NULL DEFAULT 0;
ALTER TABLE crops ADD COLUMN regional_compatibility INT NOT NULL DEFAULT 0;
ALTER TABLE crops ADD COLUMN irrigation_compatibility INT NOT NULL DEFAULT 0;
```

Wait - but I ALREADY ran these ALTER TABLE commands earlier and got `ERROR 1064 (42000) at line 2: You have an error in your SQL syntax; check the manual that corresponds to your MySQL server version for the right syntax to use near 'soil_compatibility'`

Hmm, that's weird. `ALTER TABLE crops ADD COLUMN soil_compatibility INT DEFAULT 0;` should work fine in MySQL 8.0.

Oh wait - I think the issue might be that I ran `ALTER TABLE crops ADD COLUMN IF NOT EXISTS soil_compatibility INT DEFAULT 0;` but MySQL doesn't support `IF NOT EXISTS` for ADD COLUMN! MySQL 8.0 does NOT support `IF NOT EXISTS` for ALTER TABLE ADD COLUMN. That's why I got ERROR 1064!

So I need to:
1. Check if columns already exist
2. Add them if they don't exist (without IF NOT EXISTS since MySQL doesn't support it for ADD COLUMN)

But wait - looking at my earlier attempt:
```
mysql : mysql: [Warning] Using a password on the command line interface can be insecure.
At line:1 char:48
+ ... uvida 2.0'; mysql -u kisaan_user -pshubh1244 kisaan_suvidha -e "
+                      ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (mysql: [Warning...an be insecure.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
ERROR 1064 (42000) at line 2: You have an error in your SQL syntax; check the manual that corresponds to your MySQL server version for the right syntax to use near 'soil_compatibility' 
```

So the error was at line 2, which is `ALTER TABLE crops ADD COLUMN season_compatibility INT NOT NULL DEFAULT 0;`

This means MySQL 8.0 does NOT support `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` syntax! MySQL only supports `ADD COLUMN` without `IF NOT EXISTS`.

So I need to either:
1. Drop and recreate the table (bad idea - would lose data)
2. Check if column exists before adding it (complicated in plain SQL)
3. Just try to add it and ignore the error if it already exists

Since I'm going to run the migration from scratch anyway (drop tables and recreate), let me just:
1. Drop all crop-related tables
2. Run the migration again
3. Run the seed script

But wait - I just realized something. Looking at the migration file again:

```sql
CREATE TABLE IF NOT EXISTS crops (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    ...
    soils JSON,
    ...
    water_req ENUM('Low', 'Medium', 'High') NOT NULL DEFAULT 'Medium',
    water_requirement_mm DECIMAL(10,2)	YES		NULL	
    waterlog_tolerance	enum('Low','Medium','High')	NO		Medium	
    drought_tolerance	enum('Low','Medium','High')	NO		Medium	
    temp_min	decimal(5,1)	YES		NULL	
    ...
    created_at	timestamp	NO		CURRENT_TIMESTAMP	DEFAULT_GENERATED
    updated_at	timestamp	NO		CURRENT_TIMESTAMP	DEFAULT_GENERATED on update CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES crop_categories(id) ON DELETE CASCADE,
    INDEX idx_crops_name (name),
    INDEX idx_crops_category (category_id),
    INDEX idx_crops_season (season)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

There's NO `soil_compatibility`, `season_compatibility`, `regional_compatibility`, `irrigation_compatibility` columns in this migration!

But the seed_crops.sql file expects them:
```sql
INSERT INTO crops (
    name, hindi_name, scientific_name, season,
    soils,
    n_range_min, n_range_max,
    p_range_min, p_range_max,
    k_range_min, k_range_max,
    ph_range_min, ph_range_max,
    soil_compatibility,
    season_compatibility,
    regional_compatibility,
    irrigation_compatibility,
    ...
```

So the seed_crops.sql expects columns that don't exist in the migration!

I need to either:
1. Add these columns to the migration file and re-run it
2. Or manually add these columns to the existing crops table

Since I already ran the migration, I just need to add the missing columns:

```sql
ALTER TABLE crops ADD COLUMN soil_compatibility INT DEFAULT 0;
ALTER TABLE crops ADD COLUMN season_compatibility INT NOT NULL DEFAULT 0;
ALTER TABLE crops ADD COLUMN regional_compatibility INT NOT NULL DEFAULT 0;
ALTER TABLE crops ADD COLUMN irrigation_compatibility INT NOT NULL DEFAULT 0;
```

Then run the seed again!

But wait - I tried this before and got `ERROR 1064 (42000) at line 2: You have an error in your SQL syntax; check the manual that corresponds to your MySQL server version for the right syntax to use near 'soil_compatibility'`

Hmm, that's weird. `ALTER TABLE crops ADD COLUMN soil_compatibility INT DEFAULT 0;` should work fine in MySQL 8.0!

Unless... the issue is that PowerShell is interpreting the `<` character in `ALTER TABLE crops ADD COLUMN soil_compatibility INT DEFAULT 0;` as a redirection operator!

Wait no, there's no `<` in that statement.

Let me look more carefully at the error:
```
mysql : mysql: [Warning] Using a password on the command line interface can be insecure.
At line:1 char:48
+ ... uvida 2.0'; mysql -u kisaan_user -pshubh1244 kisaan_suvidha -e "
+                      ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (mysql: [Warning...an be insecure.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
ERROR 1064 (42000) at line 2: You have an error in your SQL syntax; check the manual that corresponds to your MySQL server version for the right syntax to use near 'soil_compatibility' 
```

Wait, the error says "at line 2" and "near 'soil_compatibility'". But my ALTER TABLE statement is on line 1:

```
ALTER TABLE crops ADD COLUMN soil_compatibility INT DEFAULT 0;
```

Oh wait - I think the issue is that PowerShell is interpreting the `>` character in `INT DEFAULT 0)` as output redirection!

No wait, that doesn't make sense either. `>` at the end of `INT DEFAULT 0);` would be interpreted as output redirection only if it's at the end of the line followed by a filename.

Let me look at the actual command again:
```
mysql -u kisaan_user -pshubh1244 kisaan_suvidha -e "
ALTER TABLE crops ADD COLUMN IF NOT EXISTS soil_compatibility INT DEFAULT 0;
ALTER TABLE crops ADD COLUMN IF NOT EXISTS season_compatibility INT NOT NULL DEFAULT 0;
ALTER TABLE crops ADD COLUMN IF NOT EXISTS regional_compatibility INT NOT NULL DEFAULT 0;
ALTER TABLE crops ADD COLUMN IF NOT EXISTS irrigation_compatibility INT NOT NULL DEFAULT 0;
" 2>&1
```

The error message says line 2 has the error. Line 2 would be `ALTER TABLE crops ADD COLUMN season_compatibility INT NOT NULL DEFAULT 0;`.

But wait - PowerShell might be interpreting `<` in `<=10` or something as redirection? No, there's no `<` in that statement.

Actually, looking more carefully at the error: `ERROR 1064 (42S22) at line 2: You have an error in your SQL syntax; check the manual that corresponds to your MySQL server version for the right syntax to use near 'soil_compatibility'`

So it's saying the error is near `soil_compatibility` column name. This suggests MySQL is trying to parse `ALTER TABLE crops ADD COLUMN soil_compatibility INT NOT NULL DEFAULT 0;` but failing.

Wait - maybe MySQL 8.0 doesn't support `ADD COLUMN ... DEFAULT 0` for INT columns? No, that's standard SQL.

Actually, I think the issue might be that PowerShell is interpreting `>` in `DEFAULT 0)` as output redirection! Let me check:

`ALTER TABLE crops ADD COLUMN soil_compatibility INT DEFAULT 0;`

There's no `>` in this statement though. `DEFAULT 0);` - the `>` would need to be followed by a filename to be interpreted as redirection. But `)` comes after `0`, not `>`.

Hmm, this is strange. Let me just try running the migration again and see if it works now. Maybe the issue was something else entirely.

Actually, I think the simplest approach now is to just add the missing columns one at a time using mysql command line:

```bash
mysql -u kisaan_user -pshubh1244 kisaan_suvidha -e "ALTER TABLE crops ADD COLUMN soil_compatibility INT DEFAULT 0;"
ALTER TABLE crops ADD COLUMN season_compatibility INT NOT NULL DEFAULT 0;
ALTER TABLE crops ADD COLUMN regional_compatibility INT NOT NULL DEFAULT 0;
ALTER TABLE crops ADD COLUMN irrigation_compatibility INT NOT NULL DEFAULT 0;"
```

I already tried this and got `ERROR 1064 (42000) at line 2: You have an error in your SQL syntax; check the manual that corresponds to your MySQL server version for the right syntax to use near 'soil_compatibility'`.

Wait, that's really strange. `ALTER TABLE crops ADD COLUMN soil_compatibility INT DEFAULT 0;` should work fine in MySQL 8.0.

Unless... the MySQL server version is very old and doesn't support `ADD COLUMN`? No, that's a basic feature since MySQL 3.23.

Or maybe there's a syntax issue with how PowerShell passes the command to mysql?

Let me try writing the SQL to a file and then running it:

Actually wait - looking at my bash command output:
```
mysql : mysql: [Warning] Using a password on the command line interface can be insecure.
At line:1 char:48
+ ... uvida 2.0'; mysql -u kisaan_user -pshubh1244 kisaan_suvidha -e "
+                      ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (mysql: [Warning...an be insecure.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
ERROR 1064 (42000) at line 2: You have an error in your SQL syntax; check the manual that corresponds to your MySQL server version for the right syntax to use near 'soil_compatibility' 
```

The error says line 2, which would be `ALTER TABLE crops ADD COLUMN season_compatibility INT NOT NULL DEFAULT 0;`.

But wait - maybe PowerShell is interpreting `$` in variable names? No, there are no `$` in the SQL.

Oh wait! I think the issue might be that PowerShell is interpreting `{}` in some way? No, there's no `{}` either.

Let me just try a completely different approach. I'll write the SQL to a file and then pipe it to mysql:

```bash
echo "ALTER TABLE crops ADD COLUMN soil_compatibility INT DEFAULT 0;
ALTER TABLE crops ADD COLUMN season_compatibility INT NOT NULL DEFAULT 0;
ALTER TABLE crops ADD COLUMN regional_compatibility INT NOT NULL DEFAULT 0;
ALTER TABLE crops ADD COLUMN irrigation_compatibility INT NOT NULL DEFAULT 0;" | mysql -u kisaan_user -pshubh1244 kisaan_suvidha
```

This way PowerShell won't interpret any special characters in the SQL.

Actually wait - I just realized something. Looking at the migration file again:

```sql
-- 2. Crops master table with full agronomic parameters
CREATE TABLE IF NOT EXISTS crops (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ...
    soil_type VARCHAR(100),
    ...
    water_req ENUM('Low', 'Medium', 'High') NOT NULL DEFAULT 'Medium',
    ...
```

There's NO `soil_compatibility` column in the migration! So when I ran the migration, it created the table WITHOUT that column.

Then when I ran `Get-Content 'scripts/seed_crops.sql' | mysql -u kisaan_user -pshubh1244 kisaan_suvidha`, it tried to INSERT into `soil_compatibility` column which doesn't exist!

So I NEED to add the column first:

```sql
ALTER TABLE crops ADD COLUMN soil_compatibility INT DEFAULT 0;
ALTER TABLE crops ADD COLUMN season_compatibility INT NOT NULL DEFAULT 0;
ALTER TABLE crops ADD COLUMN regional_compatibility INT NOT NULL DEFAULT 0;
ALTER TABLE crops ADD COLUMN irrigation_compatibility INT NOT NULL DEFAULT 0;
```

And then run the seed again.

Let me do this now!</think><tool_call>
<function=bash>