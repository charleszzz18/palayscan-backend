import sys
import os
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import analyze_rice_health

def test_uploaded_image():
    img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', '2284def7bb3147d18ac931f0a3475149.jpg')
    if not os.path.exists(img_path):
        print(f"File {img_path} does not exist!")
        return

    print(f"Testing uploaded image: {img_path}")
    img = cv2.imread(img_path)
    res = analyze_rice_health(img)
    
    print("--- DIAGNOSTIC RESULTS ---")
    print(f"Primary Disease:    {res['primary_disease']} ({res['primary_disease_tl']})")
    print(f"Severity:           {res['severity_label']}")
    print(f"Health Score:       {res['health_score']:.1%}")
    print(f"Infected Area:      {res['infected_area_pct']}%")
    print(f"Confirmed Diseases: {res['confirmed_diseases']}")
    print(f"Visual Matches:     {res['visual_matches']}")
    print(f"Symptoms:           {res['disease_symptom']}")
    print(f"Why Detected:       {res['why_detected']}")
    print(f"Lesion Hotspots:    {len(res['lesion_hotspots'])} spots found")
    for i, spot in enumerate(res['lesion_hotspots'][:3]):
        print(f"  Spot #{i+1}: {spot}")

def test_dataset_samples():
    dataset_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dataset', 'Rice Disease')
    classes = ['Brown Spot', 'Blast', 'Healthy']
    for cls in classes:
        cls_dir = os.path.join(dataset_dir, cls)
        if not os.path.exists(cls_dir):
            continue
        files = [f for f in os.listdir(cls_dir) if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
        if not files:
            continue
        sample_path = os.path.join(cls_dir, files[0])
        img = cv2.imread(sample_path)
        if img is None:
            continue
        res = analyze_rice_health(img)
        print(f"\nTesting Dataset [{cls}] Sample ({files[0]}):")
        print(f"  Primary Disease: {res.get('primary_disease')}")
        print(f"  Health Score:    {res.get('health_score', 0):.1%}")
        print(f"  Visual Matches:  {res.get('visual_matches')}")

if __name__ == '__main__':
    test_uploaded_image()
    test_dataset_samples()
