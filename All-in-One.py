import re
import os
import csv

def load_typo_dict_from_csv(file_path):
    """
    CSV 파일에서 오타 사전을 불러옵니다.
    CSV는 'typo', 'correction' 두 개의 열을 가져야 합니다.
    """
    typo_dict = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader) # 헤더 건너뛰기
            for row in reader:
                if len(row) == 2:
                    typo, correction = row
                    typo_dict[typo.strip()] = correction.strip()
    except FileNotFoundError:
        print(f"경고: '{file_path}' 오타 사전을 찾을 수 없습니다. 오타 수정 없이 진행합니다.")
    except Exception as e:
        print(f"오류: 오타 사전 파일 처리 중 오류 발생 - {e}")
    return typo_dict

def clean_and_parse_vtt(file_path):
    """
    VTT 파일을 읽고, 대사가 아닌 정보/특수문자 등을 제거한 뒤,
    파싱해서 큐(cue) 딕셔너리의 리스트로 반환.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"오류: '{file_path}' 파일을 찾을 수 없습니다.")
        return None

    non_dialogue_keywords = [
        # 한국어 키워드
        "배급:", "제공:", "감독:", "제작:", "각본:", "출연:",
        # 영어 키워드
        "Presented by", "Director:", "Production:", "Screenplay:", "Starring:",
        # VTT 기본 헤더
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
                start, end_and_styles = stripped_line.split(" --> ")
                end = end_and_styles.split(" ")[0]
                current_cue = {'start': start.strip(), 'end': end.strip(), 'text': ''}
                text_buffer = []
            except ValueError:
                current_cue = None
                continue
        
        elif not stripped_line or stripped_line.isdigit() or any(keyword.lower() in line.lower() for keyword in non_dialogue_keywords):
            continue
        
        elif current_cue is not None:
            if re.search(r'[A-Z]', stripped_line) and not re.search(r'[a-z]', stripped_line):
                continue

            processed_line = re.sub(r'\[.*?\]|\(.*?\)', '', line)
            processed_line = re.sub(r"[^0-9a-zA-Z가-힣\s\-\.,?!']", '', processed_line)
            
            if processed_line.strip():
                text_buffer.append(processed_line.strip())

    if current_cue and text_buffer:
        current_cue['text'] = "\n".join(text_buffer).strip()
        if current_cue['text']:
            cues.append(current_cue)
            
    return cues

def correct_korean_typos(text, typo_dict):
    """
    주어진 오타 사전을 바탕으로 텍스트의 오타를 수정합니다.
    """
    for typo, correction in typo_dict.items():
        text = text.replace(typo, correction)
    return text

def create_final_vtt_files(en_path, kr_path, typo_dict, en_output_path, kr_output_path):
    """
    두 개의 원본 VTT 파일을 받아 모든 전처리를 거친 후
    동기화된 두 개의 최종 VTT 파일을 생성.
    """
    print("VTT 파일 처리 시작...")
    
    en_cues = clean_and_parse_vtt(en_path)
    kr_cues = clean_and_parse_vtt(kr_path)

    if not en_cues or not kr_cues:
        print("유효한 대사를 찾지 못했거나 파일 처리 중 오류가 발생했습니다. 중단합니다.")
        return

    num_synced_cues = min(len(en_cues), len(kr_cues))
    print(f"총 {len(en_cues)}개 영어 대사, {len(kr_cues)}개 한국어 대사 발견.")
    print(f"1:1 매칭 후 {num_synced_cues}개의 대사 블록으로 동기화합니다.")

    # 영어 최종 파일 생성
    with open(en_output_path, 'w', encoding='utf-8') as f_en:
        f_en.write("WEBVTT\n\n")
        for i in range(num_synced_cues):
            cue = en_cues[i]
            f_en.write(f"{i+1}\n")
            f_en.write(f"{cue['start']} --> {cue['end']}\n")
            f_en.write(f"{cue['text']}\n\n")

    # 한국어 최종 파일 생성
    with open(kr_output_path, 'w', encoding='utf-8') as f_kr:
        f_kr.write("WEBVTT\n\n")
        for i in range(num_synced_cues):
            en_timestamp_cue = en_cues[i]
            kr_text_cue = kr_cues[i]
            
            raw_kr_text = kr_text_cue['text']
            corrected_kr_text = correct_korean_typos(raw_kr_text, typo_dict)
            
            f_kr.write(f"{i+1}\n")
            f_kr.write(f"{en_timestamp_cue['start']} --> {en_timestamp_cue['end']}\n")
            f_kr.write(f"{corrected_kr_text}\n\n")

    print("-" * 30)
    print("처리 완료!")
    print(f"영어 최종 파일: '{en_output_path}'")
    print(f"한국어 최종 파일: '{kr_output_path}'")

# --- 메인 실행 로직 ---

file_basename = '7번방의선물' 

try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    script_dir = os.getcwd()

input_folder = os.path.join(script_dir, 'Input_vtt')
output_folder = os.path.join(script_dir, 'Output_vtt')
os.makedirs(output_folder, exist_ok=True)

# --- 외부 파일 경로 설정 ---
typo_csv_path = os.path.join(script_dir, 'typos.csv')
original_en_vtt = os.path.join(input_folder, f'{file_basename}_en.vtt')
original_kr_vtt = os.path.join(input_folder, f'{file_basename}_kr.vtt')
final_en_output = os.path.join(output_folder, f'{file_basename}_en_FINAL.vtt')
final_kr_output = os.path.join(output_folder, f'{file_basename}_kr_FINAL.vtt')

# --- 메인 함수 실행 ---
if os.path.exists(original_en_vtt) and os.path.exists(original_kr_vtt):
    # 1. 오타 사전 불러오기
    typo_dictionary = load_typo_dict_from_csv(typo_csv_path)
    # 2. 메인 함수에 오타 사전 전달
    create_final_vtt_files(original_en_vtt, original_kr_vtt, typo_dictionary, final_en_output, final_kr_output)
else:
    print(f"오류: '{original_en_vtt}' 또는 '{original_kr_vtt}' 파일을 찾을 수 없습니다.")
    print(f"'{input_folder}' 폴더에 파일이 있는지, 파일 이름을 정확히 설정했는지 확인해주세요.")

