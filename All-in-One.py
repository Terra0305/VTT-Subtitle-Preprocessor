import re
import os
import csv
from datetime import timedelta

# --- 유틸리티 함수들 ---

def time_to_seconds(time_str):
    """VTT 시간 형식('HH:MM:SS.mmm')을 초(float)로 변환"""
    try:
        h, m, s_ms = time_str.split(':')
        s, ms = s_ms.split('.')
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0
    except ValueError:
        # 가끔 HH:MM:SS,mmm 형식으로 오는 경우 처리
        if ',' in time_str:
            return time_to_seconds(time_str.replace(',', '.'))
        print(f"경고: 잘못된 시간 형식 '{time_str}'. 0초로 처리합니다.")
        return 0.0

def seconds_to_time(seconds):
    """초(float)를 VTT 시간 형식('HH:MM:SS.mmm')으로 변환"""
    if seconds < 0:
        seconds = 0
    td = timedelta(seconds=seconds)
    minutes, seconds = divmod(td.seconds, 60)
    hours, minutes = divmod(minutes, 60)
    milliseconds = td.microseconds // 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

def load_typo_dict_from_csv(file_path):
    """CSV 파일에서 오타 사전을 불러옴"""
    typo_dict = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
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

    non_dialogue_keywords = [
        "배급:", "제공:", "감독:", "제작:", "각본:", "출연:",
        "Presented by", "Director:", "Production:", "Screenplay:", "Starring:",
        "WEBVTT", "Kind:", "Language:"
    ]

    cues = []
    current_cue = None
    text_buffer = []

    for line in lines:
        stripped_line = line.strip()

        if "-->" in stripped_line:
            if current_cue and text_buffer:
                current_cue['text'] = "\n".join(text_buffer).strip()
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
        elif any(keyword.lower() in line.lower() for keyword in non_dialogue_keywords):
            current_cue = None
            continue
        elif current_cue is not None:
            # 전체가 대문자인 라인(배우 이름 등) 제거
            if re.fullmatch(r'[^a-z가-힣]*', stripped_line):
                 continue
            
            # 괄호 및 메뉴얼에 명시된 특수문자 제거
            processed_line = re.sub(r'\[.*?\]|\(.*?\)', '', line)
            # 허용 문자 외 모두 제거 (주의: 대사 시작 '-'는 유지)
            # 문장 중간의 -는 유지하되, #, &, 음표 등은 제거
            processed_line = re.sub(r'[#♪&]', '', processed_line) 
            
            if processed_line.strip():
                text_buffer.append(processed_line.strip())

    if current_cue and text_buffer:
        current_cue['text'] = "\n".join(text_buffer).strip()
        if current_cue['text']:
            cues.append(current_cue)

    return cues

def synchronize_cues(en_cues, kr_cues):
    """타임스탬프 오버랩을 기준으로 영어와 한국어 CUE를 동기화"""
    synced_pairs = []
    used_kr_indices = set()

    print("\n타임스탬프 기준 1:1 자막 매칭 시작...")

    for en_idx, en_cue in enumerate(en_cues):
        best_match_kr_cue = None
        best_overlap = 0
        best_match_idx = -1

        for kr_idx, kr_cue in enumerate(kr_cues):
            if kr_idx in used_kr_indices:
                continue

            # 두 CUE 간의 시간 겹침(overlap) 계산
            overlap_start = max(en_cue['start_sec'], kr_cue['start_sec'])
            overlap_end = min(en_cue['end_sec'], kr_cue['end_sec'])
            overlap_duration = max(0, overlap_end - overlap_start)

            if overlap_duration > best_overlap:
                best_overlap = overlap_duration
                best_match_kr_cue = kr_cue
                best_match_idx = kr_idx
        
        # 겹치는 부분이 0.1초 이상일 때만 유효한 매칭으로 간주
        if best_overlap > 0.1 and best_match_kr_cue:
            synced_pairs.append({
                'en_cue': en_cue,
                'kr_cue': best_match_kr_cue
            })
            used_kr_indices.add(best_match_idx)

    print(f"총 {len(synced_pairs)}개의 동기화된 자막 쌍을 찾았습니다.")
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

    # 2. CUE 동기화
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
            en_cue = pair['en_cue']
            kr_cue = pair['kr_cue']
            
            # 오타 수정 적용
            corrected_kr_text = correct_korean_typos(kr_cue['text'], typo_dict)
            
            # 타임스탬프는 영어(기준) 파일 것을 사용
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
    file_basename = '관상' 

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