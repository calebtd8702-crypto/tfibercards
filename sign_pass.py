
import subprocess
import hashlib
import json
import os
import zipfile
import shutil
import sys
from PIL import Image, ImageOps, ImageDraw

def create_manifest(pass_dir):
    """Creates a manifest.json file containing SHA1 hashes of all files."""
    manifest = {}
    for root, dirs, files in os.walk(pass_dir):
        for filename in files:
            if filename in ['manifest.json', 'signature', '.DS_Store']:
                continue
            filepath = os.path.join(root, filename)
            relpath = os.path.relpath(filepath, pass_dir)
            
            with open(filepath, 'rb') as f:
                manifest[relpath] = hashlib.sha1(f.read()).hexdigest()
    
    with open(os.path.join(pass_dir, 'manifest.json'), 'w') as f:
        json.dump(manifest, f)

def sign_manifest(pass_dir, key_pem, cert_pem, wwdr_pem, password=None):
    """Signs the manifest using openssl."""
    manifest_path = os.path.join(pass_dir, 'manifest.json')
    signature_path = os.path.join(pass_dir, 'signature')
    
    cmd = [
        'openssl', 'smime', '-binary', '-sign',
        '-certfile', wwdr_pem,
        '-signer', cert_pem,
        '-inkey', key_pem,
        '-in', manifest_path,
        '-out', signature_path,
        '-outform', 'DER'
    ]
    
    if password:
        cmd.extend(['-passin', f'pass:{password}'])
        
    try:
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as e:
        print(f"Error signing manifest: {e}")
        sys.exit(1)

def zip_pass(pass_dir, output_file):
    """Zips the directory into a .pkpass file."""
    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(pass_dir):
            for file in files:
                filepath = os.path.join(root, file)
                arcname = os.path.relpath(filepath, pass_dir)
                zipf.write(filepath, arcname)
    print(f"Created {output_file}")

if __name__ == '__main__':
    # Configuration
    PASS_DIR = 'wallet_pass'
    
    # User needs to provide these paths relative to this script
    KEY_PEM = 'certificates/key.pem' 
    CERT_PEM = 'certificates/certificate.pem'
    WWDR_PEM = 'certificates/wwdr.pem'
    PASSWORD = 'your_p12_password'

    # Data for each person
    people = [
        {
            "filename": "MichaelPurdy",
            "data": {
                "name": "Michael Purdy",
                "phone": "319-423-5405",
                "email": "michael.purdy@t-mobile.com",
                "vcard_n": "Purdy;Michael;;;",
                "vcard_fn": "Michael Purdy",
                "photo": "michael_headshot.png" 
            }
        },
        {
            "filename": "CalebDicken",
            "data": {
                "name": "Caleb Dicken",
                "phone": "515-707-9550",
                "email": "caleb.dicken1@t-mobile.com",
                "vcard_n": "Dicken;Caleb;;;",
                "vcard_fn": "Caleb Dicken",
                "photo": "profile.png"
            }
        },
        {
            "filename": "BenElfvin",
            "data": {
                "name": "Ben Elfvin",
                "phone": "515-664-5937",
                "email": "belfvin@gmail.com",
                "vcard_n": "Elfvin;Ben;;;",
                "vcard_fn": "Ben Elfvin",
                "photo": "ben_headshot.jpg",
                "title": "TV Technician"
            }
        }
    ]

    # Check certs first
    if not (os.path.exists(KEY_PEM) and os.path.exists(CERT_PEM) and os.path.exists(WWDR_PEM)):
        print("Error: Certificates not found!")
        print(f"Please place your certificates in a 'certificates' folder:")
        print(f"- {KEY_PEM}")
        print(f"- {CERT_PEM}")
        print(f"- {WWDR_PEM}")
        sys.exit(1)

    # Read the template pass.json
    with open(os.path.join(PASS_DIR, 'pass.json'), 'r') as f:
        template = json.load(f)

    for person in people:
        print(f"Generating pass for {person['data']['name']}...")
        
        # Create a temporary copy of the pass data
        person_pass = template.copy()
        
        # Update fields
        person_pass['generic']['primaryFields'][0]['value'] = person['data']['name']
        person_pass['generic']['auxiliaryFields'][0]['value'] = person['data']['phone']
        person_pass['generic']['auxiliaryFields'][1]['value'] = person['data']['email']
        
        # Title Logic
        title = person['data'].get('title', "Territory Manager")
        person_pass['generic']['secondaryFields'][0]['value'] = title

        # Update QR Code
        vcard = f"BEGIN:VCARD\nVERSION:3.0\nN:{person['data']['vcard_n']}\nFN:{person['data']['vcard_fn']}\nORG:T-Mobile;T-Fiber\nTITLE:T-Fiber {title}\nTEL;TYPE=CELL:{person['data']['phone']}\nEMAIL:{person['data']['email']}\nURL:https://www.t-mobile.com/fiber\nEND:VCARD"
        person_pass['barcode']['message'] = vcard

        # Write the specific pass.json
        with open(os.path.join(PASS_DIR, 'pass.json'), 'w') as f:
            json.dump(person_pass, f, indent=2)

        # Process Photo (Top-aligned Square Crop + Circle Mask)
        photo_src = person['data']['photo']
        if os.path.exists(photo_src):
            try:
                img = Image.open(photo_src).convert("RGBA")
                w, h = img.size
                size = min(w, h)
                
                # Crop top square (0, 0, size, size)
                if h > w:
                    # Portrait: Top square
                    img = img.crop((0, 0, w, w))
                else:
                    # Landscape: Center square
                    left = (w - h) // 2
                    img = img.crop((left, 0, left + h, h))
                
                # Mask
                mask = Image.new('L', img.size, 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0, img.size[0], img.size[1]), fill=255)
                
                output = ImageOps.fit(img, mask.size, centering=(0.5, 0.5))
                output.putalpha(mask)
                
                dest_1x = os.path.join(PASS_DIR, 'thumbnail.png')
                dest_2x = os.path.join(PASS_DIR, 'thumbnail@2x.png')
                output.save(dest_1x, "PNG")
                output.save(dest_2x, "PNG")
                
            except Exception as e:
                print(f"Error processing photo with PIL: {e}")
                shutil.copy(photo_src, os.path.join(PASS_DIR, 'thumbnail.png'))
                shutil.copy(photo_src, os.path.join(PASS_DIR, 'thumbnail@2x.png'))
        else:
            print(f"Warning: Photo {photo_src} not found!")

        # Create Manifest
        create_manifest(PASS_DIR)
        
        # Sign Manifest
        sign_manifest(PASS_DIR, KEY_PEM, CERT_PEM, WWDR_PEM)
            
        # Zip it up
        output_name = f"{person['filename']}.pkpass"
        zip_pass(PASS_DIR, output_name)
        
    print("\nAll passes generated successfully!")
