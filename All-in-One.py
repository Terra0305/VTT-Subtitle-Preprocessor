import re
import os

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
        "배급:", "제공:", "감독:", "제작:", 
        "Presented by", "Director:", "Production:", "WEBVTT"
    ] 

    cues = []
    current_cue = None
    text_buffer = []

    for line in lines:
        stripped_line = line.strip()

        if "-->" in stripped_line:
            if current_cue and text_buffer:
                current_cue['text'] = "\n".join(text_buffer).strip()
                cues.append(current_cue)
            
            try:
                start, end = stripped_line.split(" --> ")
                current_cue = {'start': start.strip(), 'end': end.strip(), 'text': ''}
                text_buffer = []
            except ValueError:
                continue
        elif not stripped_line or stripped_line.isdigit() or any(keyword in line for keyword in non_dialogue_keywords):
            continue
        elif current_cue is not None:
            processed_line = re.sub(r'\[.*?\]|\(.*?\)', '', line)
            processed_line = re.sub(r'[^0-9a-zA-Z가-힣\s\-\.,?!]', '', processed_line)
            
            if processed_line.strip():
                text_buffer.append(processed_line.strip())

    if current_cue and text_buffer:
        current_cue['text'] = "\n".join(text_buffer).strip()
        cues.append(current_cue)
        
    return cues

def correct_korean_typos(text):
    """
    미리 정의된 규칙에 따라 한국어 오타를 수정합니다.
    """
    typo_dict = {"필요고 없지": "필요도 없지"}
    for typo, correction in typo_dict.items():
        text = text.replace(typo, correction)
    return text

def create_final_vtt_files(en_path, kr_path, en_output_path, kr_output_path):
    """
    두 개의 원본 VTT 파일을 받아 모든 전처리를 거친 후
    동기화된 두 개의 최종 VTT 파일을 생성.
    """
    print("VTT 파일 처리 시작...")
    
    en_cues = clean_and_parse_vtt(en_path)
    kr_cues = clean_and_parse_vtt(kr_path)

    if en_cues is None or kr_cues is None:
        print("파일 처리 중단.")
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
            corrected_kr_text = correct_korean_typos(kr_text_cue['text'])
            
            f_kr.write(f"{i+1}\n")
            f_kr.write(f"{en_timestamp_cue['start']} --> {en_timestamp_cue['end']}\n")
            f_kr.write(f"{corrected_kr_text}\n\n")

    print("-" * 30)
    print("처리 완료!")
    print(f"영어 최종 파일: '{en_output_path}'")
    print(f"한국어 최종 파일: '{kr_output_path}'")

# --- 메인 실행 로직 ---


#'가시_en_1.vtt'와 '가시_kr_1.vtt'를 작업하려면 '가시'라고 적으면 됨
file_basename = '7번방의선물' # <--- 여기만 수정하시면 됩니다.

# --- 폴더 설정 (어디서 실행해도 되도록 절대 경로로 수정) ---
script_dir = os.path.dirname(os.path.abspath(__file__))
input_folder = os.path.join(script_dir, 'Input_vtt')
output_folder = os.path.join(script_dir, 'Output_vtt')

# 출력 폴더가 없으면 자동으로 생성
os.makedirs(output_folder, exist_ok=True)

# 설정된 기본 이름을 바탕으로 전체 파일 경로 생성
original_en_vtt = os.path.join(input_folder, f'{file_basename}_en.vtt')
original_kr_vtt = os.path.join(input_folder, f'{file_basename}_kr.vtt')
final_en_output = os.path.join(output_folder, f'{file_basename}_en_FINAL.vtt')
final_kr_output = os.path.join(output_folder, f'{file_basename}_kr_FINAL.vtt')

# 파일 존재 여부 확인 후 메인 함수 실행
if os.path.exists(original_en_vtt) and os.path.exists(original_kr_vtt):
    create_final_vtt_files(original_en_vtt, original_kr_vtt, final_en_output, final_kr_output)
else:
    print(f"오류: '{original_en_vtt}' 또는 '{original_kr_vtt}' 파일을 찾을 수 없습니다.")
    print(f"'{input_folder}' 폴더에 파일이 있는지, 파일 이름을 정확히 설정했는지 확인해주세요.")