DATASET_COLUMNS = [
    'session_key', 'meeting_key', 'driver_number', 'lap_number', 'date_start',
    'lap_duration', 'is_pit_out_lap', 'stint_number', 'tyre_age', 'compound',
    'circuit', 'year', 'exclusion_reasons', 'is_clean', 'is_racing',
]

EXCLUSION_REASONS = [
    'lap_1', 'pit_out', 'null_lap_duration', 'safety_car', 'no_stint',
    'in_lap', 'before_retirement', 'after_finish'
]

def find_stint(stints: list[dict], driver_number: int, lap_number: int) -> dict | None:
    '''
    Finds the stint for a given driver and lap number.
    Returns the stint if it exists, otherwise returns None.
    Raises a ValueError if multiple stints are found for the same driver and lap number.
    '''
    matches = []
    for stint in stints:
        if stint['driver_number'] == driver_number and stint['lap_start'] <= lap_number <= stint['lap_end']:
            matches.append(stint)
    if len(matches) == 0:
        return None
    elif len(matches) == 1:
        return matches[0]
    else:
        raise ValueError(f"Multiple stints found for driver {driver_number} at lap {lap_number}")

def add_stint_data(laps: list[dict], stints: list[dict]) -> list[dict]:
    '''
    Adds the tyre age, compound & stint number to the laps.
    Laps with no matching stint are kept with tyre_age, compound & stint_number set to None.
    Laps with multiple matching stints raise a ValueError.
    Returns the laps with the tyre age added.
    '''
    result = []
    for lap in laps:
        stint = find_stint(stints, lap['driver_number'], lap['lap_number'])
        if stint is None:
            result.append({**lap, "tyre_age": None, "compound": None, "stint_number": None})
        else:
            result.append({**lap, "tyre_age":stint['tyre_age_at_start'] + lap['lap_number'] - stint['lap_start'], "compound": stint['compound'], "stint_number": stint['stint_number']})
    return result

def has_lap(laps: list[dict], driver_number: int, lap_number: int) -> bool:
    '''
    Returns True if the driver has a lap with this lap number.
    '''
    for lap in laps:
        if lap['driver_number'] == driver_number and lap['lap_number'] == lap_number:
            return True
    return False

def race_distance(laps: list[dict]) -> int | None:
    '''
    The race distance in laps: the highest lap_number that has a lap_duration.
    Some 2023 races list one extra lap per finisher after the chequered flag,
    with no lap_duration, so the highest lap_number alone is one too many.
    Returns None if no lap has a lap_duration.
    '''
    timed = [lap['lap_number'] for lap in laps if lap['lap_duration'] is not None]
    if not timed:
        return None
    return max(timed)

def find_safety_car_disruption_laps(race_control: list[dict]) -> set:
    '''
    Takes in race_control as a list of dicts.
    Returns the laps affected by the safety car (with a buffer of 1 lap before and 1 after) as a set.
    A safety car still out at the chequered flag lasts until that lap.
    '''

    affected_laps = set()
    start_lap = None
    for r in race_control:
        if r['category'] == 'SafetyCar' and 'deployed' in r['message'].lower():
            start_lap = r['lap_number']
        if r['category'] == 'SafetyCar' and ('in this lap' in r['message'].lower() or 'ending' in r['message'].lower()):
            end_lap = r['lap_number']
            if start_lap is None:
                raise ValueError(f"Safety car ended on lap {end_lap} but was never deployed")
            for i in range(start_lap - 1, end_lap + 2):
                affected_laps.add(i)
            start_lap = None
    if start_lap is not None:
        # A race can finish under the safety car: no "in this lap" message, the chequered flag ends it.
        chequered = [r['lap_number'] for r in race_control
                     if r['category'] == 'Flag' and r['flag'] == 'CHEQUERED' and r['lap_number'] is not None]
        if not chequered:
            raise ValueError(f'Safety car on {start_lap} has no end message')
        for i in range(start_lap - 1, max(chequered) + 2):
            affected_laps.add(i)
    return affected_laps

def exclusion_reasons(lap: dict, stints: list[dict], laps: list[dict], safety_car_laps: set) -> list[str]:
    '''
    Returns every reason to exclude one lap, or an empty list if the lap is clean.
    Takes the lap, plus the stints and laps of its race and the safety car affected laps.
    Laps with no matching stint can't be in_lap or before_retirement.
    A lap past the race distance (see race_distance) is after_finish, and the
    lap before it is the driver's real last lap, not before_retirement.
    '''
    reasons = []
    distance = race_distance(laps)
    if lap["lap_number"] == 1:
        reasons.append('lap_1')
    if lap["is_pit_out_lap"]:
        reasons.append('pit_out')
    if lap['lap_duration'] is None:
        reasons.append('null_lap_duration')
    if lap['lap_number'] in safety_car_laps:
        reasons.append('safety_car')
    if distance is not None and lap['lap_number'] > distance:
        reasons.append('after_finish')
    stint = find_stint(stints, lap['driver_number'], lap['lap_number'])
    if stint is None:
        reasons.append('no_stint')
        return reasons
    if lap['lap_number'] == stint['lap_end']:
        next_lap_number = lap['lap_number'] + 1
        if find_stint(stints, lap['driver_number'], next_lap_number) is not None:
            reasons.append('in_lap')
        elif has_lap(laps, lap['driver_number'], next_lap_number) and (distance is None or next_lap_number <= distance):
            reasons.append('before_retirement')
    return reasons

def add_exclusion_reasons(laps: list[dict], stints: list[dict], race_control: list[dict]) -> list[dict]:
    '''
    Adds the exclusion reasons for each lap.
    Returns the laps with the exclusion reasons added.
    '''
    result = []
    affected_laps = find_safety_car_disruption_laps(race_control)
    for lap in laps:
        reasons = exclusion_reasons(lap, stints, laps, affected_laps)
        result.append({**lap, 'exclusion_reasons': reasons})
    return result

def is_racing_lap(reasons: list) -> bool:
    '''
    Takes list of reasons as input, returns True/False based on if a lap is considered a racing lap or not.

    '''
    for reason in reasons:
        if reason in ['safety_car', 'null_lap_duration', 'no_stint', 'in_lap', 'pit_out', 'after_finish']:
            return False
    return True

def is_clean_lap(reasons:list) -> bool:
    '''
    Checks if a lap is a clean lap by making sure reasons length is 0.
    Meaning, nothing triggered add_exclusion_reasons, so the lap is a valid clean lap.
    Returns True/False
    '''
    return len(reasons) == 0

def build_race_rows(laps: list[dict], stints: list[dict], race_control: list[dict], circuit, year):
    '''
    Takes in the laps, stints, race control, circuit and year.
    Uses our existing functions add_stint_data, add_exclusion_reasons to gather the stint data and get reasons.
    Labels each lap wih whether it's a clean lap, racing lap, both, or neither.
    Returns the race rows labelled.
    '''
    stint_data = add_stint_data(laps, stints)
    labelled = add_exclusion_reasons(stint_data, stints, race_control)
    rows = []
    for lap in labelled:
        reasons = lap['exclusion_reasons']
        racing_lap = is_racing_lap(reasons)
        clean_lap = is_clean_lap(reasons)
        data = {**lap, 'circuit': circuit, 'year': year, 'is_clean': clean_lap, 'is_racing': racing_lap}
        rows.append(data)

    return rows



def keep_dataset_columns(rows: list[dict]) -> list[dict]:
    '''
    Takes rows from build_race_rows.
    Returns new rows with only DATASET_COLUMNS, in that order.
    Raises a KeyError if a row is missing one of them.
    '''
    result = []
    for row in rows:
        result.append({column: row[column] for column in DATASET_COLUMNS})
    return result

def count_missing(rows: list[dict]) -> dict:
    '''
    Given the race rows, returns dictionary of all columns with their missing values count.
    '''
    result = {column: 0 for column in DATASET_COLUMNS}
    for r in rows:
        for col in DATASET_COLUMNS:
             if r[col] is None:
                result[col] += 1
    return result

def count_duplicate_keys(rows: list[dict]) -> int:
    '''
    Counts how many rows repeat a key that's already been seen
    '''
    seen = set()
    count = 0
    for r in rows:
        key = (r['session_key'], r['driver_number'], r['lap_number'])
        if key in seen:
            count += 1
        else:
            seen.add(key) 

    return count

def count_reasons(rows: list[dict]) -> dict:
    '''
    Takes in the lap rows, and counts number of reasons in each lap. A lap with two reasons counts both.
    '''
    result = {reason: 0 for reason in EXCLUSION_REASONS}
    for row in rows:
        for reason in row['exclusion_reasons']:
            result[reason] += 1
    return result

def race_quality(rows: list[dict]) -> dict:
    '''
    Takes one race's dataset rows.
    Returns one flat dict: rows, duplicate_keys, clean, racing,
    missing_<column> for every column, and a count for every exclusion reason.
    '''
    result = {
        'rows': len(rows),
        'duplicate_keys': count_duplicate_keys(rows),
        'clean': 0,
        'racing': 0,
    }
    for row in rows:
        if row['is_clean']:
            result['clean'] += 1
        if row['is_racing']:
            result['racing'] += 1
    for column, count in count_missing(rows).items():
        result['missing_' + column] = count
    result.update(count_reasons(rows))
    return result

def markdown_table(report: dict, keys: list[str], headers: list[str]) -> list[str]:
    '''
    Takes a dict of race name -> race_quality dict, the keys to show and their headers.
    Returns the lines of a Markdown table with one row per race.
    '''
    lines = ['| Race | ' + ' | '.join(headers) + ' |', '|---|' + '---:|' * len(keys)]
    for name, quality in report.items():
        lines.append(f'| {name} | ' + ' | '.join(f'{quality[key]:,}' for key in keys) + ' |')
    return lines

def quality_markdown(report: dict) -> str:
    '''
    Takes a dict of race name -> race_quality dict.
    Returns the data-quality report as Markdown, with three tables: overview,
    missing values and exclusion reasons. Columns with no missing values
    anywhere are named in one sentence instead of the missing-values table.
    '''
    missing = [c for c in DATASET_COLUMNS if any(q['missing_' + c] > 0 for q in report.values())]
    complete = [c for c in DATASET_COLUMNS if c not in missing]

    lines = ['# Data quality', '',
             'Generated by `scripts/build_dataset.py` from `data/processed/lap_dataset.parquet`.',
             'Do not edit by hand. Clean and racing laps are defined by is_clean_lap and is_racing_lap in src/pitwall/processing.py.', '',
             '## Overview', '']
    lines += markdown_table(report, ['rows', 'duplicate_keys', 'clean', 'racing'],
                            ['Rows', 'Duplicate keys', 'Clean', 'Racing'])

    lines += ['', '## Missing values', '']
    if missing:
        lines += markdown_table(report, ['missing_' + c for c in missing], [f'`{c}`' for c in missing])
        lines.append('')
    lines.append('No missing values in: ' + ', '.join(f'`{c}`' for c in complete) + '.')

    lines += ['', '## Exclusion reasons', '',
              'A lap can have more than one reason, so a row can add up to more than its excluded laps.', '']
    lines += markdown_table(report, EXCLUSION_REASONS, [f'`{r}`' for r in EXCLUSION_REASONS])
    return '\n'.join(lines) + '\n'

def build_driver_names(records: list[dict]) -> dict[int, dict]:
    '''
    Driver names for one session, from the OpenF1 /drivers records.

    records: /drivers records of one session, each with "driver_number" (int),
        "name_acronym", "first_name", "last_name" and "team_name"; any
        of the three name fields may be missing or None

    returns: dict driver_number -> {"acronym", "name", "team"}, e.g.
    {1: {"acronym": "VER", "name": "Max Verstappen", "team": "Red Bull Racing"}}.
    A missing field is None, never an empty string.

    raises ValueError if a driver_number appears twice (the join key would be ambiguous).
    '''
    names = {}
    for record in records:
        number = record["driver_number"]
        if number in names:
            raise ValueError(f"Driver number {number} appears twice in one session")
        full = " ".join(part for part in (record.get("first_name"), record.get("last_name")) if part)
        names[number] = {"acronym": record.get("name_acronym") or None, "name": full or None,
                         "team": record.get("team_name") or None}
    return names


WET_COMPOUNDS = {"INTERMEDIATE", "WET"}


def race_exclusion_reasons(stints: list[dict], race_control: list[dict]) -> list[str]:
    '''
    Why a whole race can't go in the dataset (empty if it can).

    stints: OpenF1 /stints records of the race, each with "compound"
    race_control: OpenF1 /race_control records of the race, each with "category", "flag" and "date"

    returns: list of reasons, any of
        "no_data": no stints or no race_control messages were returned
        "wet_tyres": any car ran an intermediate or wet tyre (the simulator is dry-only, and a
            mixed-condition race can't be told from a dry one by lap time alone)
        "red_flag": a red flag was shown before the chequered flag (a red flag allows a free
            tyre change and a standing restart, which the simulator doesn't model); one shown
            after the chequered flag (pit-lane closure) doesn't count
    '''
    if not stints or not race_control:
        return ["no_data"]
    reasons = []
    flags = [r for r in race_control if r["category"] == "Flag"]
    chequered = [r["date"] for r in flags if r["flag"] == "CHEQUERED"]
    end = min(chequered) if chequered else None
    if any(r["flag"] == "RED" and (end is None or r["date"] < end) for r in flags):
        reasons.append("red_flag")
    if any(s["compound"] in WET_COMPOUNDS for s in stints):
        reasons.append("wet_tyres")
    return reasons
