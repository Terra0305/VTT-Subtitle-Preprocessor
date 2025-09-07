import re
import os
import csv
from datetime import timedelta

# --- Utility Functions ---

def time_to_seconds(time_str):
    """Converts VTT time format ('HH:MM:SS.mmm') to seconds (float)."""
    try:
        time_str_cleaned = time_str.replace(',', '.')
        parts = time_str_cleaned.split(':')
        h = int(parts[0])
        m = int(parts[1])
        s_ms = parts[2].split('.')
        s = int(s_ms[0])
        ms = int(s_ms[1]) if len(s_ms) > 1 else 0
        return h * 3600 + m * 60 + s + ms / 1000.0
    except (ValueError, IndexError) as e:
        print(f"Warning: Invalid time format '{time_str}'. Treating as 0 seconds. Error: {e}")
        return 0.0

def seconds_to_time(seconds):
    """Converts seconds (float) to VTT time format ('HH:MM:SS.mmm')."""
    if seconds < 0:
        seconds = 0
    total_milliseconds = round(seconds * 1000)
    
    hours, remainder = divmod(total_milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}.{int(milliseconds):03d}"

def load_typo_dict_from_csv(file_path):
    """Loads a typo dictionary from a CSV file."""
    typo_dict = {}
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if len(row) == 2:
                    typo, correction = row
                    typo_dict[typo.strip()] = correction.strip()
    except FileNotFoundError:
        print(f"Warning: Typo dictionary '{file_path}' not found. Proceeding without typo correction.")
    except Exception as e:
        print(f"Error: An error occurred while processing the typo dictionary file - {e}")
    return typo_dict

def correct_korean_typos(text, typo_dict):
    """Corrects typos in the text based on the provided dictionary."""
    # Process specific known broken characters first
    text = text.replace("又", "또") # Example of fixing a broken character
    
    for typo, correction in typo_dict.items():
        text = text.replace(typo, correction)
    return text

# --- Core Logic Functions ---

def parse_and_clean_vtt(file_path):
    """Reads, parses, and cleans a VTT file, returning a list of cues."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return []
    
    non_dialogue_keywords = [
        "배급:", "제공:", "감독:", "제작:", "각본:", "출연:", "공동제작",
        "Presented by", "Director:", "Production:", "Screenplay:", "Starring:",
        "LOTTE ENTERTAINMENT", "A TPS COMPANY", "WEBVTT", "Kind:", "Language:",
        "ANNALS OF THE JOSEON DYNASTY", "THE TREACHEROUS", "NEUNGJU"
    ]

    cues = []
    current_cue = None
    text_buffer = []

    for line in lines:
        stripped_line = line.strip()

        if "-->" in stripped_line:
            if current_cue and text_buffer:
                current_cue['text'] = " ".join(text_buffer).strip()
                if current_cue['text']:
                    cues.append(current_cue)
            
            try:
                start_str, end_str_full = stripped_line.split(" --> ")
                end_str = end_str_full.split(" ")[0]
                current_cue = {
                    'start_sec': time_to_seconds(start_str),
                    'end_sec': time_to_seconds(end_str),
                    'text': ''
                }
                text_buffer = []
            except (ValueError, IndexError):
                current_cue = None
                continue
        elif not stripped_line or stripped_line.isdigit():
            continue
        elif any(keyword.lower() in stripped_line.lower() for keyword in non_dialogue_keywords):
            current_cue = None
            continue
        elif current_cue is not None:
            if re.match(r'^[A-Z0-9\s,.:\-]+$', stripped_line) and len(re.findall(r'[a-z]', stripped_line)) < 3:
                 continue
            
            processed_line = re.sub(r'\[.*?\]|\(.*?\)', '', stripped_line)
            processed_line = re.sub(r'[#♪&]', '', processed_line)
            
            if re.fullmatch(r'"[A-Z\s,-]+"', processed_line):
                continue
            
            if processed_line:
                text_buffer.append(processed_line)

    if current_cue and text_buffer:
        current_cue['text'] = " ".join(text_buffer).strip()
        if current_cue['text']:
            cues.append(current_cue)

    return cues

def merge_cues_in_group(group):
    """Merges a group of cues into a single cue."""
    if not group:
        return None
    
    start_sec = min(c['start_sec'] for c in group)
    end_sec = max(c['end_sec'] for c in group)
    
    sorted_group = sorted(group, key=lambda x: x['start_sec'])
    text = " ".join(c['text'] for c in sorted_group)
    
    return {'start_sec': start_sec, 'end_sec': end_sec, 'text': text}

def synchronize_cues(en_cues, kr_cues):
    """
    Groups and synchronizes overlapping cues with added constraints to prevent over-merging.
    """
    # --- CONFIGURATION ---
    # Maximum time gap between two cues to be considered part of the same group
    MAX_TIME_GAP_SECONDS = 1.0 
    # Maximum total duration for a single merged group
    MAX_GROUP_DURATION_SECONDS = 15.0 

    synced_pairs = []
    
    used_en_indices = set()
    used_kr_indices = set()

    print("\nStarting cue synchronization with improved grouping logic...")

    for i in range(len(en_cues)):
        if i in used_en_indices:
            continue

        # Start a new potential group with the current English cue
        group_en_indices = {i}
        group_kr_indices = set()
        
        # --- Group Expansion ---
        queue_to_check = [('en', i)]
        
        while queue_to_check:
            lang, current_idx = queue_to_check.pop(0)

            if lang == 'en':
                current_cue_obj = en_cues[current_idx]
                target_cues = kr_cues
                target_indices_set = group_kr_indices
                used_target_indices = used_kr_indices
                next_lang = 'kr'
            else: # lang == 'kr'
                current_cue_obj = kr_cues[current_idx]
                target_cues = en_cues
                target_indices_set = group_en_indices
                used_target_indices = used_en_indices
                next_lang = 'en'
            
            for j, target_cue in enumerate(target_cues):
                if j in used_target_indices or j in target_indices_set:
                    continue
                
                # Check for overlap or very close proximity
                gap = max(current_cue_obj['start_sec'], target_cue['start_sec']) - min(current_cue_obj['end_sec'], target_cue['end_sec'])
                
                # Condition to add to group: must overlap or be very close
                if gap < MAX_TIME_GAP_SECONDS:
                    # Check if adding this cue exceeds the max duration
                    potential_group_start = min(en_cues[idx]['start_sec'] for idx in group_en_indices.union({j} if next_lang == 'en' else set()))
                    potential_group_end = max(en_cues[idx]['end_sec'] for idx in group_en_indices.union({j} if next_lang == 'en' else set()))
                    
                    if (potential_group_end - potential_group_start) > MAX_GROUP_DURATION_SECONDS:
                        continue # Skip adding this cue as it would make the group too long

                    target_indices_set.add(j)
                    queue_to_check.append((next_lang, j))

        if group_en_indices and group_kr_indices:
            en_group_cues = [en_cues[idx] for idx in group_en_indices]
            kr_group_cues = [kr_cues[idx] for idx in group_kr_indices]

            merged_en = merge_cues_in_group(en_group_cues)
            merged_kr = merge_cues_in_group(kr_group_cues)

            if merged_en and merged_kr:
                merged_kr['start_sec'] = merged_en['start_sec']
                merged_kr['end_sec'] = merged_en['end_sec']
                
                synced_pairs.append({'en_cue': merged_en, 'kr_cue': merged_kr})

                used_en_indices.update(group_en_indices)
                used_kr_indices.update(group_kr_indices)
    
    synced_pairs.sort(key=lambda x: x['en_cue']['start_sec'])

    print(f"Successfully created {len(synced_pairs)} synchronized cue groups.")
    return synced_pairs

# --- Main Execution Function ---

def process_vtt_files(en_path, kr_path, typo_dict, en_output_path, kr_output_path):
    """Executes the full VTT preprocessing and synchronization pipeline."""
    
    en_cues = parse_and_clean_vtt(en_path)
    kr_cues = parse_and_clean_vtt(kr_path)
    print(f"File loading and cleaning complete: {len(en_cues)} English cues, {len(kr_cues)} Korean cues.")

    if not en_cues or not kr_cues:
        print("Error: No valid cues found. Aborting process.")
        return

    synced_data = synchronize_cues(en_cues, kr_cues)

    with open(en_output_path, 'w', encoding='utf-8') as f_en, \
         open(kr_output_path, 'w', encoding='utf-8') as f_kr:
        
        f_en.write("WEBVTT\n\n")
        f_kr.write("WEBVTT\n\n")
        
        for i, pair in enumerate(synced_data):
            en_cue = pair['en_cue']
            kr_cue = pair['kr_cue']
            
            start_time = seconds_to_time(en_cue['start_sec'])
            end_time = seconds_to_time(en_cue['end_sec'])
            
            # Write English cue
            f_en.write(f"{i+1}\n")
            f_en.write(f"{start_time} --> {end_time}\n")
            f_en.write(f"{en_cue['text']}\n\n")
            
            # Correct typos and write Korean cue
            corrected_kr_text = correct_korean_typos(kr_cue['text'], typo_dict)
            f_kr.write(f"{i+1}\n")
            f_kr.write(f"{start_time} --> {end_time}\n")
            f_kr.write(f"{corrected_kr_text}\n\n")
            
    print("-" * 30)
    print("Processing complete!")
    print(f"Final English file: '{en_output_path}'")
    print(f"Final Korean file: '{kr_output_path}'")


# --- Script Execution Section ---
if __name__ == "__main__":
    file_basename = '간신' 

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        script_dir = os.getcwd()

    input_folder = os.path.join(script_dir, 'Input_vtt')
    output_folder = os.path.join(script_dir, 'Output_vtt')
    os.makedirs(output_folder, exist_ok=True)

    typo_csv_path = os.path.join(script_dir, 'typos.csv')
    original_en_vtt = os.path.join(input_folder, f'{file_basename}_en_1.vtt')
    original_kr_vtt = os.path.join(input_folder, f'{file_basename}_kr_1.vtt')
    final_en_output = os.path.join(output_folder, f'{file_basename}_en_FINAL.vtt')
    final_kr_output = os.path.join(output_folder, f'{file_basename}_kr_FINAL.vtt')

    if os.path.exists(original_en_vtt) and os.path.exists(original_kr_vtt):
        typo_dictionary = load_typo_dict_from_csv(typo_csv_path)
        process_vtt_files(original_en_vtt, original_kr_vtt, typo_dictionary, final_en_output, final_kr_output)
    else:
        print(f"Error: Input files not found.")
        print(f"  - English file path: '{original_en_vtt}'")
        print(f"  - Korean file path: '{original_kr_vtt}'")
        print(f"Please check if the files exist in the '{input_folder}' folder.")
