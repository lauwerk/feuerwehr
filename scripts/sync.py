#!/usr/bin/env python3
"""
Feuerwehr Lernbar – Cache Sync
Holt alle Topics, Posts und Dateien von der API und speichert sie lokal.
"""

import requests
import json
import os
import time
import hashlib
from pathlib import Path
from urllib.parse import urlparse

BASE_URL = "https://feuerwehr-lernbar.bayern/api"
CACHE_DIR = Path("cache")
FILES_DIR = CACHE_DIR / "files"
FILES_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; FeuerwehrLernCache/1.0)"
})

def fetch_json(url, params=None):
    """Fetch JSON von der API mit Retry."""
    for attempt in range(3):
        try:
            r = SESSION.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  Fehler bei {url}: {e} (Versuch {attempt+1}/3)")
            time.sleep(2 ** attempt)
    return None

def fetch_all_paginated(endpoint, label="Einträge"):
    """
    Universelle paginierte Abfrage.
    Die API gibt cursor = ID des letzten Elements zurück.
    Nächste Seite: cursor=<letzter_cursor>, die API gibt dann
    Einträge mit ID < cursor zurück. Fertig wenn data leer.
    """
    items = []
    cursor = None
    while True:
        params = {"limit": 100}
        if cursor is not None:
            params["cursor"] = cursor
        data = fetch_json(f"{BASE_URL}/{endpoint}", params)
        if not data:
            break
        # API kann Liste oder Dict mit "data"-Key zurückgeben
        if isinstance(data, list):
            batch = data
            next_cursor = None
        else:
            batch = data.get("data", [])
            next_cursor = data.get("cursor")
        
        if not batch:
            break
        items.extend(batch)
        print(f"  {label}: {len(items)}")
        
        # Kein weiterer Cursor → fertig
        if not next_cursor:
            break
        # Cursor hat sich nicht verändert → Endlosschleife verhindern
        if next_cursor == cursor:
            break
        cursor = next_cursor
        time.sleep(0.3)
    return items

def fetch_post_detail(slug):
    """Einzelnen Post mit vollem Inhalt abrufen."""
    return fetch_json(f"{BASE_URL}/posts/{slug}")

def download_file(url, filename):
    """Datei herunterladen, nur wenn noch nicht vorhanden oder geändert."""
    dest = FILES_DIR / filename
    try:
        # HEAD-Request für ETag/Last-Modified
        head = SESSION.head(url, timeout=15, allow_redirects=True)
        remote_size = int(head.headers.get("content-length", 0))
        
        if dest.exists() and dest.stat().st_size == remote_size and remote_size > 0:
            return "skip"
        
        r = SESSION.get(url, timeout=60, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return "downloaded"
    except Exception as e:
        print(f"    Download-Fehler {url}: {e}")
        return "error"

def safe_filename(url, title=""):
    """Sicheren Dateinamen aus URL ableiten."""
    path = urlparse(url).path
    name = os.path.basename(path)
    if not name or "." not in name:
        # Fallback: Hash
        name = hashlib.md5(url.encode()).hexdigest()[:12]
    return name

def main():
    print("=== Feuerwehr Lernbar Cache Sync ===\n")
    
    # 1. Tag-Baum
    print("📂 Lade Tag-Struktur...")
    tags = fetch_json(f"{BASE_URL}/tags/tree")
    if tags:
        (CACHE_DIR / "tags.json").write_text(
            json.dumps(tags, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  ✓ {len(tags)} Hauptkategorien gespeichert")

    # 2. Alle Topics
    print("\n📚 Lade Topics...")
    topics = fetch_all_paginated("topics", "Topics")
    (CACHE_DIR / "topics.json").write_text(
        json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  ✓ {len(topics)} Topics gespeichert")

    # 3. Alle Posts (Metadaten)
    print("\n📄 Lade Posts (Metadaten)...")
    posts = fetch_all_paginated("posts", "Posts")
    print(f"  ✓ {len(posts)} Posts gefunden")

    # 4. Post-Details + Datei-Links sammeln
    print("\n🔍 Lade Post-Details und sammle Datei-Links...")
    file_queue = []
    detailed_posts = []
    
    for i, post in enumerate(posts):
        slug = post.get("slug")
        if not slug:
            detailed_posts.append(post)
            continue
        
        detail = fetch_post_detail(slug)
        if detail:
            detailed_posts.append(detail)
            # Datei-Links aus Attachments/Content extrahieren
            for att in detail.get("attachments", []):
                url = att.get("url") or att.get("file_url")
                if url:
                    file_queue.append({
                        "url": url,
                        "post_slug": slug,
                        "title": att.get("title", ""),
                        "type": att.get("mime_type", "")
                    })
        else:
            detailed_posts.append(post)
        
        if (i + 1) % 20 == 0:
            print(f"  Details: {i+1}/{len(posts)}")
        time.sleep(0.2)

    (CACHE_DIR / "posts.json").write_text(
        json.dumps(detailed_posts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  ✓ {len(detailed_posts)} Posts mit Details gespeichert")

    # 5. Dateien herunterladen
    if file_queue:
        print(f"\n📎 Lade {len(file_queue)} Dateien herunter...")
        stats = {"downloaded": 0, "skip": 0, "error": 0}
        file_index = []
        
        for item in file_queue:
            fname = safe_filename(item["url"], item.get("title", ""))
            status = download_file(item["url"], fname)
            stats[status] = stats.get(status, 0) + 1
            item["local_file"] = fname if status != "error" else None
            file_index.append(item)
            
            if stats["downloaded"] % 10 == 0 and stats["downloaded"] > 0:
                print(f"  Heruntergeladen: {stats['downloaded']}, übersprungen: {stats['skip']}")
            time.sleep(0.3)
        
        (CACHE_DIR / "files_index.json").write_text(
            json.dumps(file_index, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  ✓ {stats['downloaded']} neu, {stats['skip']} unverändert, {stats['error']} Fehler")
    else:
        print("\n📎 Keine Datei-Anhänge gefunden (API-Struktur prüfen)")
        (CACHE_DIR / "files_index.json").write_text("[]", encoding="utf-8")

    # 6. Manifest: Sync-Zeitstempel
    import datetime
    manifest = {
        "synced_at": datetime.datetime.utcnow().isoformat() + "Z",
        "topics_count": len(topics),
        "posts_count": len(detailed_posts),
        "files_count": len(file_queue)
    }
    (CACHE_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    
    print(f"\n✅ Sync abgeschlossen: {manifest['synced_at']}")
    print(f"   Topics: {manifest['topics_count']} | Posts: {manifest['posts_count']} | Dateien: {manifest['files_count']}")

if __name__ == "__main__":
    main()