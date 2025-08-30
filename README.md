# VTT Subtitle Preprocessor (VTT 자막 전처리기)

A simple and effective Python script to clean, parse, and synchronize dual-language (English/Korean) `.vtt` subtitle files for data analysis. This project was initially created to preprocess subtitle data for a project with GIST (Gwangju Institute of Science and Technology).

---

## ✨ Key Features

* **Metadata Removal:** Automatically removes non-dialogue lines such as headers and production credits.
* **Text Cleaning:** Deletes bracketed text `[...]` `(...)` and unnecessary special characters.
* **Timestamp Synchronization:** Aligns the timestamps of the Korean subtitle file to match the English file, ensuring perfect 1:1 cue correspondence.
* **Structured I/O:** Reads raw `.vtt` files from an `Input_vtt` directory and saves the processed files to an `Output_vtt` directory.
* **Typo Correction:** Includes a function to fix predefined common typos in the Korean subtitles.

---

## 🛠️ Tech Stack

* **Python 3**
* Built-in libraries: `re`, `os`

---

## 🚀 How to Use

1.  **Prepare Your Files:**
    * Place your raw English (`*_en_1.vtt`) and Korean (`*_kr_1.vtt`) subtitle files inside the `Input_vtt` folder.
    * The script `All-in-One.py` should be in the root directory, alongside the `Input_vtt` and `Output_vtt` folders.

    ```
    .
    ├── 📁 Input_vtt
    │   ├── movie_en_1.vtt
    │   └── movie_kr_1.vtt
    ├── 📁 Output_vtt
    └── 🐍 All-in-One.py
    ```

2.  **Set the Target File:**
    * Open the `All-in-One.py` script.
    * Find the following line and change the filename base to the one you want to process.

    ```python
    # Change 'movie' to your file's base name
    file_basename = 'movie' 
    ```

3.  **Run the Script:**
    * Execute the script from your terminal.

    ```bash
    python All-in-One.py
    ```

4.  **Check the Output:**
    * The processed `*_en_FINAL.vtt` and `*_kr_FINAL.vtt` files will be saved in the `Output_vtt` folder.

---
