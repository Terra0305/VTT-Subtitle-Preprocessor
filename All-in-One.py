import re
import os
import logging

# --- 1. 로깅 설정 ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    
    log_filename = 'vtt_cleaning.log'
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# --- 2. 핵심 클리닝 함수 ---

def clean_vtt_file(input_path: str, output_path: str):
    """
    VTT 파일을 읽어 가장 안전한 규칙만 적용하여 클리닝합니다.
    1. 대괄호 [], 소괄호 () 안의 내용을 제거합니다.
    2. 특정 특수문자(#, ♪, &)를 제거합니다.
    """
    logger.info(f"'{input_path}' 파일 클리닝 시작...")
    try:
        with open(input_path, 'r', encoding='utf-8') as infile, \
             open(output_path, 'w', encoding='utf-8') as outfile:
            
            for line in infile:
                # 타임스탬프, 숫자, WEBVTT, 빈 줄 등 구조적인 부분은 그대로 유지
                if "-->" in line or line.strip().isdigit() or "WEBVTT" in line or not line.strip():
                    outfile.write(line)
                    continue

                # 대사 라인에 대해서만 클리닝 수행
                # 1. 괄호 안 내용 제거
                cleaned_line = re.sub(r'\[.*?\]|\(.*?\)', '', line)
                # 2. 특정 특수문자 제거 (#, ♪, &)
                cleaned_line = re.sub(r'[#♪&]', '', cleaned_line)

                # 클리닝 후 내용이 남아있으면 파일에 쓰기
                if cleaned_line.strip():
                    outfile.write(cleaned_line)

        logger.info(f"클리닝 완료. 결과 파일: '{output_path}'")
        return True
    except FileNotFoundError:
        logger.error(f"입력 파일 '{input_path}'를 찾을 수 없습니다.")
        return False
    except Exception as e:
        logger.error(f"'{input_path}' 파일 처리 중 오류 발생: {e}")
        return False

# --- 3. 메인 실행 함수 ---

def main():
    """
    지정된 파일에 대해 안전한 클리닝 작업을 수행합니다.
    """
    
    # ⭐️ 여기만 수정해서 사용 ⭐️
    file_basename = '가시' 

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        script_dir = os.getcwd()

    input_folder = os.path.join(script_dir, 'Input_vtt')
    output_folder = os.path.join(script_dir, 'Output_vtt')
    os.makedirs(output_folder, exist_ok=True)

    # 처리할 파일 목록 정의
    files_to_process = {
        'en': os.path.join(input_folder, f'{file_basename}_en_1.vtt'),
        'kr': os.path.join(input_folder, f'{file_basename}_kr_1.vtt')
    }
    
    logger.info("="*50)
    logger.info(f"'{file_basename}' 파일 기본 클리닝 시작")

    all_files_exist = True
    for lang, path in files_to_process.items():
        if not os.path.exists(path):
            logger.error(f"입력 파일을 찾을 수 없습니다: '{path}'")
            all_files_exist = False
    
    if not all_files_exist:
        logger.error(f"'{input_folder}' 폴더에 파일이 있는지 확인해주세요. 처리를 중단합니다.")
        return

    # 각 파일에 대해 클리닝 함수 호출
    for lang, input_path in files_to_process.items():
        output_path = os.path.join(output_folder, f'{file_basename}_{lang}_CLEANED.vtt')
        clean_vtt_file(input_path, output_path)
    
    logger.info("-" * 30)
    logger.info("✨ 모든 처리 완료! ✨")
    logger.info(f"결과물은 '{output_folder}' 폴더를 확인하세요.")
    logger.info(f"상세 처리 과정은 'vtt_cleaning.log' 파일을 확인하세요.")
    logger.info("="*50)


# --- 4. 스크립트 실행 ---
if __name__ == "__main__":
    main()