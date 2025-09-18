import os
import base64
from PIL import Image
from functools import lru_cache
from openai import OpenAI
import cv2
from ultralytics import YOLO

# OpenAIクライアントを初期化（新API対応）
client = None

def init_openai_client():
    """OpenAI API クライアントの遅延初期化"""
    global client
    if client is None:
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            try:
                client = OpenAI(api_key=api_key)
            except TypeError as e:
                print(f"OpenAI client initialization error (buttai): {e}")
                client = None
            except Exception as e:
                print(f"OpenAI client initialization error (buttai): {e}")
                client = None

# グローバルモデル変数
model = None
model_conf = 0.3

def load_model(model_name='yolov8n', conf=0.3):
    """
    ultralytics YOLOv8 Nanoモデルをロードします。
    model_name: 'yolov8n' など
    conf: 信頼度閾値
    """
    global model, model_conf
    try:
        model_path = f"{model_name}.pt"
        
        # モデルファイルが存在しない場合の処理
        if not os.path.exists(model_path):
            print(f"Model file {model_path} not found. Downloading...")
            model = YOLO(model_name)  # 自動ダウンロード
        else:
            model = YOLO(model_path)
        
        model_conf = conf
        
        # モデル設定の最適化
        model.overrides['verbose'] = False  # ログを削減
        
        print("YOLO model loaded successfully")
        return True
        
    except ImportError:
        print("Ultralytics YOLO not available. Object detection disabled.")
        return False
    except Exception as e:
        print(f"Error loading YOLO model: {e}")
        return False


def classify_scene_label(image_path):
    """YOLO未検出時のフォールバック: OpenAI Visionでシーン名（英語ラベル）を1つ返す"""
    try:
        init_openai_client()
        if client is None:
            return ''

        # 候補シーン（英語ラベル）
        scene_labels = [
            'mountain','lake','sea','forest','temple','shrine','castle','tower',
            'city skyline','night view','sunset','waterfall','park','river','snow','desert','island'
        ]

        # 画像をBase64化
        with open(image_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')

        # 指示: リストから最も適切な1つを選びJSONで返す
        messages = [
            {
                'role': 'system',
                'content': 'あなたは写真のシーンを判定する分類器です。出力は必ずJSONのみで返し、説明は不要です。'
            },
            {
                'role': 'user',
                'content': [
                    { 'type': 'text', 'text': (
                        '次の候補から最も当てはまるシーンを1つ選び、{"scene":"<label>"} のJSONのみで出力してください。\n'
                        f"候補: {', '.join(scene_labels)}"
                    ) },
                    { 'type': 'image_url', 'image_url': { 'url': f'data:image/jpeg;base64,{b64}' } }
                ]
            }
        ]

        res = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=messages,
            temperature=0.2,
            max_tokens=20,
            response_format={"type": "json_object"},
            timeout=15
        )

        import json as _json
        payload = _json.loads(res.choices[0].message.content)
        scene = str(payload.get('scene', '')).strip()
        return scene

    except Exception:
        return ''


@lru_cache(maxsize=256)
def get_emotion(label):
    """物体ラベルから感情キーワードを取得（API専用版）"""
    try:
        init_openai_client()
        if client is not None:
            prompt = f"物体「{label}」を見たときに、多くの人が直感的に抱く一般的な感情を、日本語の形容詞または形容動詞で一語だけ答えてください（例: 穏やかな, 壮大な, 静かな）。名詞や句は不可。"
            
            # 新API形式 + GPT-3.5-turbo使用
            response = client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[{'role':'user','content':prompt}],
                max_tokens=5,  # トークン数削減
                temperature=0.1,  # 温度下げて安定性向上
                timeout=10  # タイムアウト設定
            )
            
            emotion = response.choices[0].message.content.strip().strip('「」"')
            if emotion:
                return emotion
        
        # クライアントが初期化できない場合またはレスポンスが空の場合
        return 'api error'
                
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return 'api error'

def process_buttai(image_path):
    """画像パスを受け取り、物体検出と感情ラベルを返す（最適化版）"""
    # モデル初期化
    if model is None:
        if not load_model():
            return 'api error', 'no_model'  # モデル読み込み失敗時

    try:
        # 1) 画像読み込み＆最適化
        img = cv2.imread(image_path)
        if img is None:
            return 'api error', 'invalid_image'
        
        # より効率的なリサイズ（アスペクト比保持）
        h, w = img.shape[:2]
        scale = min(320/w, 320/h)
        new_w, new_h = int(w*scale), int(h*scale)
        img_small = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        # 2) YOLOv8 Nano推論（最適化設定）
        results = model(
            img_small, 
            conf=model_conf,
            verbose=False,  # ログ抑制
            save=False,     # 保存しない
            show=False      # 表示しない
        )
        
        r = results[0]
        boxes = r.boxes
        
        if boxes is None or len(boxes) == 0:
            # シーン分類フォールバック（名称→感情抽出）
            scene_label = classify_scene_label(image_path)
            if scene_label:
                emotion_fb = get_emotion(scene_label)
                if emotion_fb and emotion_fb != 'api error':
                    return emotion_fb, f"scene:{scene_label}"
            return 'api error', 'no_object'

        # 3) 最も信頼度の高い物体を選択
        confs = boxes.conf.cpu().numpy()
        cls_ids = boxes.cls.cpu().numpy().astype(int)
        
        idx = confs.argmax()
        confidence = confs[idx]
        
        # 信頼度チェック
        if confidence < 0.25:  # 閾値を少し下げて検出率向上
            # シーン分類フォールバック（名称→感情抽出）
            scene_label = classify_scene_label(image_path)
            if scene_label:
                emotion_fb = get_emotion(scene_label)
                if emotion_fb and emotion_fb != 'api error':
                    return emotion_fb, f"scene:{scene_label}"
            return 'api error', 'low_confidence'
        
        label = r.names[cls_ids[idx]]
        print(f"=== 物体検出結果 ===")
        print(f"選択された物体: {label} (信頼度: {confidence:.3f})")
        emotion = get_emotion(label)
        print(f"取得された感情: {emotion}")
        print("===================")
        
        return emotion, label
        
    except Exception as e:
        print(f"Object detection error: {e}")
        return 'api error', 'error' 