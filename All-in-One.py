import re
import os
import csv
import logging
from datetime import timedelta

# --- 1. 설정값 ---

# 대사가 아닌 것으로 판단하여 제거할 키워드 목록
NON_DIALOGUE_KEYWORDS = [
    "배급:", "제공:", "감독:", "제작:", "각본:", "출연:", "공동제작",
    "Presented by", "Director:", "Production:", "Screenplay:", "Starring:",
    "LOTTE ENTERTAINMENT", "A TPS COMPANY", "WEBVTT", "Kind:", "Language:",
]

# --- 2. 로깅 설정 ---

# 로그 생성
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 로그 포맷 정의
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# 스트림 핸들러 (콘솔 출력)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# 파일 핸들러 (파일 저장)
file_handler = logging.FileHandler('vtt_processing.log', encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


# --- 3. 유틸리티 함수들 ---

def time_to_seconds(time_str: str) -> float:
    """VTT 시간 형식('HH:MM:SS.mmm')을 초(float)로 변환"""
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
        logger.warning(f"잘못된 시간 형식 '{time_str}'. 0초로 처리합니다. 오류: {e}")
        return 0.0

def seconds_to_time(seconds: float) -> str:
    """초(float)를 VTT 시간 형식('HH:MM:SS.mmm')으로 변환"""
    if seconds < 0:
        seconds = 0
    total_milliseconds = round(seconds * 1000)
    
    hours, remainder = divmod(total_milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds_val, milliseconds = divmod(remainder, 1000)
    
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds_val):02d}.{int(milliseconds):03d}"

def load_typo_dict_from_csv(file_path: str) -> dict:
    """CSV 파일에서 오타 사전을 불러옴"""
    typo_dict = {}
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader)  # 헤더 건너뛰기
            for row in reader:
                if len(row) == 2:
                    typo, correction = row
                    typo_dict[typo.strip()] = correction.strip()
        logger.info(f"'{file_path}'에서 {len(typo_dict)}개의 오타 규칙을 불러왔습니다.")
    except FileNotFoundError:
        logger.warning(f"'{file_path}' 오타 사전을 찾을 수 없음. 오타 수정 없이 진행합니다.")
    except Exception as e:
        logger.error(f"오타 사전 파일 처리 중 오류 발생: {e}")
    return typo_dict

def correct_korean_typos(text: str, typo_dict: dict) -> str:
    """주어진 오타 사전을 바탕으로 텍스트의 오타를 수정"""
    for typo, correction in typo_dict.items():
        text = text.replace(typo, correction)
    return text


# --- 4. 핵심 로직 함수들 ---

def parse_and_clean_vtt(file_path: str) -> list:
    """VTT 파일을 읽고 파싱 및 클리닝하여 CUE 리스트 반환"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        logger.error(f"'{file_path}' 파일을 찾을 수 없습니다.")
        return []
    
    cues = []
    current_cue = None
    text_buffer = []

    for line in lines:
        stripped_line = line.strip()

        if "-->" in stripped_line:
            if current_cue and text_buffer:
                # 여러 줄의 텍스트를 줄바꿈 문자로 합쳐서 화자 구분(-) 유지
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
        elif any(keyword.lower() in stripped_line.lower() for keyword in NON_DIALOGUE_KEYWORDS):
            current_cue = None # 이 키워드가 포함된 큐는 건너뛰기
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
        current_cue['text'] = "\n".join(text_buffer).strip()
        if current_cue['text']:
            cues.append(current_cue)

    return cues

def merge_cues_in_group(group: list) -> dict or None:
    """자막 그룹을 병합하여 하나의 자막으로 만듦"""
    if not group:
        return None
    
    start_sec = min(c['start_sec'] for c in group)
    end_sec = max(c['end_sec'] for c in group)
    
    sorted_group = sorted(group, key=lambda x: x['start_sec'])
    # 여러 CUE의 텍스트를 줄바꿈으로 합침
    text = "\n".join(c['text'] for c in sorted_group)
    
    return {'start_sec': start_sec, 'end_sec': end_sec, 'text': text}

def synchronize_cues(en_cues: list, kr_cues: list) -> list:
    """어순 차이를 고려하여 겹치는 자막들을 그룹화하고 동기화"""
    synced_pairs = []
    used_kr_indices = set()
    processed_en_groups = []

    logger.info("시간대 겹침 기준 자막 그룹화 및 동기화 시작...")

    for i, en_cue in enumerate(en_cues):
        # 이미 처리된 그룹에 속한 영어 자막은 건너뜀
        if any(en_cue in group for group in processed_en_groups):
            continue

        # 1. 초기 겹침 그룹 찾기
        overlapping_group_en = {en_cue['start_sec']: en_cue}
        overlapping_group_kr = {}
        
        for j, kr_cue in enumerate(kr_cues):
            if j in used_kr_indices:
                continue
            
            if max(en_cue['start_sec'], kr_cue['start_sec']) < min(en_cue['end_sec'], kr_cue['end_sec']):
                overlapping_group_kr[kr_cue['start_sec']] = kr_cue
        
        if not overlapping_group_kr:
            continue

        # 2. 그룹 확장
        while True:
            new_en_found = False
            new_kr_found = False

            group_kr_start = min(c['start_sec'] for c in overlapping_group_kr.values())
            group_kr_end = max(c['end_sec'] for c in overlapping_group_kr.values())
            
            for en2_cue in en_cues:
                if en2_cue['start_sec'] not in overlapping_group_en:
                    if max(group_kr_start, en2_cue['start_sec']) < min(group_kr_end, en2_cue['end_sec']):
                        overlapping_group_en[en2_cue['start_sec']] = en2_cue
                        new_en_found = True
            
            group_en_start = min(c['start_sec'] for c in overlapping_group_en.values())
            group_en_end = max(c['end_sec'] for c in overlapping_group_en.values())

            for kr2_idx, kr2_cue in enumerate(kr_cues):
                if kr2_idx not in used_kr_indices and kr2_cue['start_sec'] not in overlapping_group_kr:
                    if max(group_en_start, kr2_cue['start_sec']) < min(group_en_end, kr2_cue['end_sec']):
                        overlapping_group_kr[kr2_cue['start_sec']] = kr2_cue
                        new_kr_found = True
            
            if not new_en_found and not new_kr_found:
                break
        
        # 3. 그룹 병합 및 결과 추가
        merged_en = merge_cues_in_group(list(overlapping_group_en.values()))
        merged_kr = merge_cues_in_group(list(overlapping_group_kr.values()))

        if merged_en and merged_kr:
            merged_kr['start_sec'] = merged_en['start_sec']
            merged_kr['end_sec'] = merged_en['end_sec']
            
            synced_pairs.append({'en_cue': merged_en, 'kr_cue': merged_kr})
            
            processed_en_groups.append(list(overlapping_group_en.values()))
            for kr_cue_in_group in overlapping_group_kr.values():
                for kr_idx, original_kr_cue in enumerate(kr_cues):
                    if kr_cue_in_group == original_kr_cue:
                        used_kr_indices.add(kr_idx)
                        break
    
    synced_pairs.sort(key=lambda x: x['en_cue']['start_sec'])
    logger.info(f"총 {len(synced_pairs)}개의 동기화된 자막 그룹을 생성했습니다.")
    return synced_pairs

def write_vtt_file(output_path: str, cues: list, language: str, typo_dict: dict = None):
    """결과 CUE를 VTT 파일 형식으로 저장"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("WEBVTT\n\n")
            for i, cue_data in enumerate(cues):
                start_time = seconds_to_time(cue_data['en_cue']['start_sec'])
                end_time = seconds_to_time(cue_data['en_cue']['end_sec'])
                
                if language == 'kr' and typo_dict:
                    text = correct_korean_typos(cue_data['kr_cue']['text'], typo_dict)
                elif language == 'kr':
                    text = cue_data['kr_cue']['text']
                else: # language == 'en'
                    text = cue_data['en_cue']['text']
                
                f.write(f"{i+1}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{text}\n\n")
    except Exception as e:
        logger.error(f"'{output_path}' 파일 작성 중 오류 발생: {e}")
        return False
    return True


# --- 5. 메인 실행 함수 ---

def main():
    """전체 VTT 전처리 및 동기화 파이프라인 실행"""
    
    # ⭐️ 여기만 수정해서 사용 ⭐️
    file_basename = '개를훔치는완벽한방법' 

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        script_dir = os.getcwd()

    input_folder = os.path.join(script_dir, 'Input_vtt')
    output_folder = os.path.join(script_dir, 'Output_vtt')
    os.makedirs(output_folder, exist_ok=True)

    typo_csv_path = os.path.join(script_dir, 'typos.csv')
    original_en_vtt = os.path.join(input_folder, f'{file_basename}_en.vtt')
    original_kr_vtt = os.path.join(input_folder, f'{file_basename}_kr.vtt')
    final_en_output = os.path.join(output_folder, f'{file_basename}_en_FINAL.vtt')
    final_kr_output = os.path.join(output_folder, f'{file_basename}_kr_FINAL.vtt')

    if not (os.path.exists(original_en_vtt) and os.path.exists(original_kr_vtt)):
        logger.error("입력 파일을 찾을 수 없습니다.")
        logger.error(f"  - 영어 파일 예상 경로: '{original_en_vtt}'")
        logger.error(f"  - 한국어 파일 예상 경로: '{original_kr_vtt}'")
        logger.error(f"'{input_folder}' 폴더에 파일이 있는지 확인해주세요.")
        return

    logger.info("="*50)
    logger.info(f"'{file_basename}' 파일 처리 시작")
    
    typo_dictionary = load_typo_dict_from_csv(typo_csv_path)
    
    en_cues = parse_and_clean_vtt(original_en_vtt)
    kr_cues = parse_and_clean_vtt(original_kr_vtt)
    logger.info(f"파일 파싱 및 클리닝 완료: 영어 {len(en_cues)}개, 한국어 {len(kr_cues)}개 CUE")

    if not en_cues or not kr_cues:
        logger.error("유효한 CUE를 찾지 못해 처리를 중단합니다.")
        return

    synced_data = synchronize_cues(en_cues, kr_cues)

    logger.info("최종 VTT 파일 생성 중...")
    
    write_vtt_file(final_en_output, synced_data, 'en')
    write_vtt_file(final_kr_output, synced_data, 'kr', typo_dictionary)
            
    logger.info("-" * 30)
    logger.info("✨ 처리 완료! ✨")
    logger.info(f"영어 최종 파일: '{final_en_output}'")
    logger.info(f"한국어 최종 파일: '{final_kr_output}'")
    logger.info(f"상세 처리 과정은 'vtt_processing.log' 파일을 확인하세요.")
    logger.info("="*50)


# --- 6. 스크립트 실행 ---
if __name__ == "__main__":
    main()