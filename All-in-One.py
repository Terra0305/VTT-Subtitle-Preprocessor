import re
import os
import csv
from datetime import timedelta

# --- 유틸리티 함수들 ---

def time_to_seconds(time_str):
    """VTT 시간 형식('HH:MM:SS.mmm')을 초(float)로 변환"""
    try:
        # 쉼표(,)를 점(.)으로 일관되게 변경
        time_str_cleaned = time_str.replace(',', '.')
        parts = time_str_cleaned.split(':')
        h = int(parts[0])
        m = int(parts[1])
        s_ms = parts[2].split('.')
        s = int(s_ms[0])
        ms = int(s_ms[1]) if len(s_ms) > 1 else 0
        return h * 3600 + m * 60 + s + ms / 1000.0
    except (ValueError, IndexError) as e:
        print(f"경고: 잘못된 시간 형식 '{time_str}'. 0초로 처리합니다. 오류: {e}")
        return 0.0

def seconds_to_time(seconds):
    """초(float)를 VTT 시간 형식('HH:MM:SS.mmm')으로 변환"""
    if seconds < 0:
        seconds = 0
    # round to nearest millisecond to avoid precision issues
    total_milliseconds = round(seconds * 1000)
    
    hours, remainder = divmod(total_milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}.{int(milliseconds):03d}"

def load_typo_dict_from_csv(file_path):
    """CSV 파일에서 오타 사전을 불러옴"""
    typo_dict = {}
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f: # utf-8-sig for BOM
            reader = csv.reader(f)
            next(reader)  # 헤더 건너뛰기
            for row in reader:
                if len(row) == 2:
                    typo, correction = row
                    typo_dict[typo.strip()] = correction.strip()
    except FileNotFoundError:
        print(f"경고: '{file_path}' 오타 사전을 찾을 수 없음. 오타 수정 없이 진행합니다.")
    except Exception as e:
        print(f"오류: 오타 사전 파일 처리 중 오류 발생 - {e}")
    return typo_dict

def correct_korean_typos(text, typo_dict):
    """주어진 오타 사전을 바탕으로 텍스트의 오타를 수정"""
    for typo, correction in typo_dict.items():
        text = text.replace(typo, correction)
    return text

# --- 핵심 로직 함수들 ---

def parse_and_clean_vtt(file_path):
    """VTT 파일을 읽고 파싱 및 클리닝하여 CUE 리스트 반환"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"오류: '{file_path}' 파일을 찾을 수 없습니다.")
        return []
    
    # NOTE: 배우 이름 등은 대문자로만 이뤄진 경우가 많으므로 키워드에 추가
    non_dialogue_keywords = [
        "배급:", "제공:", "감독:", "제작:", "각본:", "출연:", "공동제작",
        "Presented by", "Director:", "Production:", "Screenplay:", "Starring:",
        "LOTTE ENTERTAINTAINMENT", "A TPS COMPANY", "WEBVTT", "Kind:", "Language:",
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
        # non_dialogue_keywords에 포함된 단어가 있으면 해당 큐 전체를 건너뛰기
        elif any(keyword.lower() in stripped_line.lower() for keyword in non_dialogue_keywords):
            current_cue = None # 이 키워드가 포함된 큐는 아예 시작하지 않음
            continue
        elif current_cue is not None:
             # 배경 정보 (e.g. "THE GORYEO ERA...") 제거 - 영어 대문자와 콜론(:) 조합
            if re.match(r'^[A-Z\s,:]+$', stripped_line):
                continue

            # 괄호 및 메뉴얼에 명시된 특수문자 제거
            processed_line = re.sub(r'\[.*?\]|\(.*?\)', '', stripped_line)
            processed_line = re.sub(r'[#♪&]', '', processed_line)
            
            # 따옴표로만 이루어진 라인(배우 이름) 제거
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
    """자막 그룹을 병합하여 하나의 자막으로 만듦"""
    if not group:
        return None
    
    # 그룹 내 모든 자막의 최소 시작 시간과 최대 종료 시간 계산
    start_sec = min(c['start_sec'] for c in group)
    end_sec = max(c['end_sec'] for c in group)
    
    # 텍스트를 시간 순서대로 정렬하여 병합
    sorted_group = sorted(group, key=lambda x: x['start_sec'])
    text = " ".join(c['text'] for c in sorted_group)
    
    return {'start_sec': start_sec, 'end_sec': end_sec, 'text': text}

def synchronize_cues(en_cues, kr_cues):
    """어순 차이를 고려하여 겹치는 자막들을 그룹화하고 동기화"""
    synced_pairs = []
    
    # 이미 처리된 한국어 자막 인덱스를 추적
    used_kr_indices = set()

    print("\n시간대 겹침 기준 자막 그룹화 및 동기화 시작...")

    for i, en_cue in enumerate(en_cues):
        
        overlapping_group_en = [en_cue]
        overlapping_group_kr = []
        
        # 현재 영어 자막과 겹치는 한국어 자막 찾기
        for j, kr_cue in enumerate(kr_cues):
            if j in used_kr_indices:
                continue
            
            overlap_start = max(en_cue['start_sec'], kr_cue['start_sec'])
            overlap_end = min(en_cue['end_sec'], kr_cue['end_sec'])
            
            if overlap_end > overlap_start:
                overlapping_group_kr.append(kr_cue)
        
        # 겹치는 한국어 자막이 없으면 다음 영어 자막으로
        if not overlapping_group_kr:
            continue

        # --- 그룹 확장 ---
        # 겹치는 한국어 자막들과 또 겹치는 다른 영어/한국어 자막들을 찾아 그룹 확장
        while True:
            new_en_found = False
            new_kr_found = False

            # 1. 현재 그룹의 한국어 자막들과 겹치는 새로운 영어 자막 찾기
            group_kr_start = min(c['start_sec'] for c in overlapping_group_kr)
            group_kr_end = max(c['end_sec'] for c in overlapping_group_kr)
            
            for en2_idx, en2_cue in enumerate(en_cues):
                if en2_cue in overlapping_group_en:
                    continue
                
                if max(group_kr_start, en2_cue['start_sec']) < min(group_kr_end, en2_cue['end_sec']):
                    overlapping_group_en.append(en2_cue)
                    new_en_found = True
            
            # 2. 현재 그룹의 영어 자막들과 겹치는 새로운 한국어 자막 찾기
            group_en_start = min(c['start_sec'] for c in overlapping_group_en)
            group_en_end = max(c['end_sec'] for c in overlapping_group_en)

            for kr2_idx, kr2_cue in enumerate(kr_cues):
                if kr2_cue in overlapping_group_kr:
                    continue

                if max(group_en_start, kr2_cue['start_sec']) < min(group_en_end, kr2_cue['end_sec']):
                    overlapping_group_kr.append(kr2_cue)
                    new_kr_found = True
            
            # 더 이상 그룹에 추가될 자막이 없으면 확장 종료
            if not new_en_found and not new_kr_found:
                break
        
        # 병합된 그룹을 결과에 추가
        merged_en = merge_cues_in_group(overlapping_group_en)
        merged_kr = merge_cues_in_group(overlapping_group_kr)

        if merged_en and merged_kr:
            # 병합된 그룹의 타임스탬프를 영어 기준으로 통일
            merged_kr['start_sec'] = merged_en['start_sec']
            merged_kr['end_sec'] = merged_en['end_sec']
            
            # 중복 추가 방지
            is_duplicate = False
            for pair in synced_pairs:
                if pair['en_cue']['start_sec'] == merged_en['start_sec'] and pair['en_cue']['text'] == merged_en['text']:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                synced_pairs.append({'en_cue': merged_en, 'kr_cue': merged_kr})

                # 이 그룹에 포함된 모든 한국어 자막을 '사용됨'으로 표시
                for kr_cue_in_group in overlapping_group_kr:
                    for kr_idx, original_kr_cue in enumerate(kr_cues):
                        if kr_cue_in_group == original_kr_cue:
                            used_kr_indices.add(kr_idx)
                            break
    
    # 최종 결과를 시간순으로 정렬
    synced_pairs.sort(key=lambda x: x['en_cue']['start_sec'])

    print(f"총 {len(synced_pairs)}개의 동기화된 자막 그룹을 생성했습니다.")
    return synced_pairs

# --- 메인 실행 함수 ---

def process_vtt_files(en_path, kr_path, typo_dict, en_output_path, kr_output_path):
    """전체 VTT 전처리 및 동기화 파이프라인 실행"""
    
    # 1. 각 언어 파일 파싱 및 클리닝
    en_cues = parse_and_clean_vtt(en_path)
    kr_cues = parse_and_clean_vtt(kr_path)
    print(f"파일 로딩 및 클리닝 완료: 영어 {len(en_cues)}개, 한국어 {len(kr_cues)}개 CUE")

    if not en_cues or not kr_cues:
        print("오류: 유효한 CUE를 찾지 못했습니다. 처리를 중단합니다.")
        return

    # 2. CUE 동기화 (그룹화 및 병합 로직 사용)
    synced_data = synchronize_cues(en_cues, kr_cues)

    # 3. 최종 VTT 파일 생성
    # 영어 파일
    with open(en_output_path, 'w', encoding='utf-8') as f_en:
        f_en.write("WEBVTT\n\n")
        for i, pair in enumerate(synced_data):
            cue = pair['en_cue']
            start_time = seconds_to_time(cue['start_sec'])
            end_time = seconds_to_time(cue['end_sec'])
            f_en.write(f"{i+1}\n")
            f_en.write(f"{start_time} --> {end_time}\n")
            f_en.write(f"{cue['text']}\n\n")
    
    # 한국어 파일
    with open(kr_output_path, 'w', encoding='utf-8') as f_kr:
        f_kr.write("WEBVTT\n\n")
        for i, pair in enumerate(synced_data):
            kr_cue = pair['kr_cue']
            en_cue = pair['en_cue'] # 타임스탬프는 영어 기준
            
            # 오타 수정 적용
            corrected_kr_text = correct_korean_typos(kr_cue['text'], typo_dict)
            
            start_time = seconds_to_time(en_cue['start_sec'])
            end_time = seconds_to_time(en_cue['end_sec'])

            f_kr.write(f"{i+1}\n")
            f_kr.write(f"{start_time} --> {end_time}\n")
            f_kr.write(f"{corrected_kr_text}\n\n")
            
    print("-" * 30)
    print("처리 완료!")
    print(f"영어 최종 파일: '{en_output_path}'")
    print(f"한국어 최종 파일: '{kr_output_path}'")


# --- 스크립트 실행 부분 ---
if __name__ == "__main__":
    # ⭐️ 여기만 수정해서 사용 ⭐️
    file_basename = '검사외전' 

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        script_dir = os.getcwd()

    # 폴더 및 파일 경로 설정
    input_folder = os.path.join(script_dir, 'Input_vtt')
    output_folder = os.path.join(script_dir, 'Output_vtt')
    os.makedirs(output_folder, exist_ok=True)

    typo_csv_path = os.path.join(script_dir, 'typos.csv')
    original_en_vtt = os.path.join(input_folder, f'{file_basename}_en.vtt')
    original_kr_vtt = os.path.join(input_folder, f'{file_basename}_kr.vtt')
    final_en_output = os.path.join(output_folder, f'{file_basename}_en_FINAL.vtt')
    final_kr_output = os.path.join(output_folder, f'{file_basename}_kr_FINAL.vtt')

    if os.path.exists(original_en_vtt) and os.path.exists(original_kr_vtt):
        typo_dictionary = load_typo_dict_from_csv(typo_csv_path)
        process_vtt_files(original_en_vtt, original_kr_vtt, typo_dictionary, final_en_output, final_kr_output)
    else:
        print(f"오류: 입력 파일을 찾을 수 없습니다.")
        print(f"  - 영어 파일 경로: '{original_en_vtt}'")
        print(f"  - 한국어 파일 경로: '{original_kr_vtt}'")
        print(f"'{input_folder}' 폴더에 파일이 있는지 확인해주세요.")