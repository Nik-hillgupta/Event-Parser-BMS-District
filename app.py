import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
import base64
import re
from io import BytesIO
import xlsxwriter

# Infer category for sources that don't have native tags (District, AllEvents)
def infer_category(text):
    text = text.lower()
    if any(kw in text for kw in ["comedy", "standup", "comic"]): return "Comedy"
    if any(kw in text for kw in ["music", "dj", "concert", "band", "gig"]): return "Music"
    if any(kw in text for kw in ["workshop", "class", "learn"]): return "Workshop"
    if any(kw in text for kw in ["theatre", "drama", "play"]): return "Theatre"
    if any(kw in text for kw in ["kids", "children", "family"]): return "Kids"
    if any(kw in text for kw in ["festival", "expo", "fair", "market"]): return "Festival/Expo"
    if any(kw in text for kw in ["party", "club", "nightlife"]): return "Party"
    if any(kw in text for kw in ["spiritual", "meditation", "yoga"]): return "Spirituality"
    return "Other"

def parse_bookmyshow(html_text, city):
    soup = BeautifulSoup(html_text, 'html.parser')
    cards = soup.select('a.sc-133848s-11')
    events = []

    for card in cards:
        try:
            event_name = card.find('h3').text.strip()
            venue = card.select('div.FnmcD')[0].text.strip()
            category = card.select('div.bsZIkT')[0].text.strip()
            price = card.select('div.bsZIkT')[1].text.strip()
            link = 'https://in.bookmyshow.com' + card['href']

            img_tag = card.find('img')
            img_url = img_tag['src'] if img_tag else ''
            date_text = ''

            # Improved base64 regex
          match = re.search(r'ie-([A-Za-z0-9%]+)', img_url)
date_text = ''
if match:
    try:
        date_text = base64.b64decode(match.group(1)).decode('utf-8')
    except Exception:
        pass
            events.append({
                'City': city,
                'Event Name': event_name,
                'Venue': venue,
                'Category': category,
                'Price': price,
                'Date': date_text,
                'Link': link,
                'Promoted': 'Yes' if 'PROMOTED' in card.text else 'No',
                'Source': 'BookMyShow',
                'Comment': ''
            })
        except Exception:
            continue

    return pd.DataFrame(events)

def parse_district(html_text, city):
    soup = BeautifulSoup(html_text, 'html.parser')
    cards = soup.select('a.dds-h-full')
    events = []

    for card in cards:
        try:
            event_name = card.find('h5').text.strip()
            spans = card.find_all('span')
            date_text = spans[0].text.strip()
            venue = spans[1].text.strip()
            price = spans[2].text.strip()
            link = card['href']
            category = infer_category(event_name + ' ' + venue)
            events.append({
                'City': city,
                'Event Name': event_name,
                'Venue': venue,
                'Category': category,
                'Price': price,
                'Date': date_text,
                'Link': link,
                'Promoted': 'No',
                'Source': 'District',
                'Comment': ''
            })
        except Exception:
            continue
    return pd.DataFrame(events)

def parse_allevents(html_text, city):
    soup = BeautifulSoup(html_text, 'html.parser')
    cards = soup.select('li.event-card')
    events = []

    for card in cards:
        try:
            event_name = card.find('h3').text.strip()
            venue = card.find('div', class_='subtitle').text.strip()
            date = card.find('div', class_='date').text.strip()
            price_div = card.find('div', class_='price')
            price = price_div.text.strip() if price_div else 'Free'
            link = card.get('data-link', '')
            category = infer_category(event_name + ' ' + venue)

            events.append({
                'City': city,
                'Event Name': event_name,
                'Venue': venue,
                'Category': category,
                'Price': price,
                'Date': date,
                'Link': link,
                'Promoted': 'No',
                'Source': 'AllEvents',
                'Comment': ''
            })
        except Exception:
            continue
    return pd.DataFrame(events)

def remove_duplicates(df):
    if 'Event Name' not in df.columns or 'Venue' not in df.columns:
        return df

    df['dedup_key'] = df['Event Name'].str.lower().str.strip() + df['Venue'].str.lower().str.strip()
    deduped = df.drop_duplicates(subset='dedup_key', keep='first')
    dupes = df[df.duplicated('dedup_key', keep='first')]

    for idx in dupes.index:
        match_key = df.loc[idx, 'dedup_key']
        orig_idx = deduped[deduped['dedup_key'] == match_key].index[0]
        orig_sources = deduped.loc[orig_idx, 'Source']
        new_source = df.loc[idx, 'Source']
        if new_source not in orig_sources:
            deduped.at[orig_idx, 'Source'] = orig_sources + ", " + new_source
        deduped.at[orig_idx, 'Comment'] = 'Duplicate removed from ' + new_source

    return deduped.drop(columns='dedup_key')

# Streamlit UI
st.set_page_config(page_title="Pixie Super Parser", layout="wide")
st.title("📦 Pixie Super Parser")
st.markdown("Parse BookMyShow, District, and AllEvents HTML dumps into clean structured Excel.")

if 'files_to_parse' not in st.session_state:
    st.session_state.files_to_parse = []

with st.form("file_form"):
    file = st.file_uploader("Choose HTML File", type=["txt", "html", "htm"])
    col1, col2 = st.columns([2, 2])
    city = col1.text_input("Enter City")
    source = col2.selectbox("Select Source", ["BookMyShow", "District", "AllEvents"])
    add_button = st.form_submit_button("Add File")

    if add_button and file and city:
        st.session_state.files_to_parse.append({
            'file': file,
            'filename': file.name,
            'city': city,
            'source': source
        })

st.subheader("📄 Files to Parse")
for i, f in enumerate(st.session_state.files_to_parse):
    st.write(f"{i+1}. {f['source']} | {f['city']} | {f['filename']}")

if st.button("🔍 Run Parser"):
    parsed_data = {'BookMyShow': [], 'District': [], 'AllEvents': []}

    for entry in st.session_state.files_to_parse:
        file_text = entry['file'].read().decode('utf-8')
        source = entry['source']
        city = entry['city']

        if source == 'BookMyShow':
            df = parse_bookmyshow(file_text, city)
        elif source == 'District':
            df = parse_district(file_text, city)
        elif source == 'AllEvents':
            df = parse_allevents(file_text, city)
        else:
            df = pd.DataFrame()

        parsed_data[source].append(df)

    bms_df = pd.concat(parsed_data['BookMyShow'], ignore_index=True) if parsed_data['BookMyShow'] else pd.DataFrame()
    district_df = pd.concat(parsed_data['District'], ignore_index=True) if parsed_data['District'] else pd.DataFrame()
    ae_df = pd.concat(parsed_data['AllEvents'], ignore_index=True) if parsed_data['AllEvents'] else pd.DataFrame()

    st.subheader("📦 Parsed Data by Source")
    if not bms_df.empty:
        st.markdown("### 🎟️ BookMyShow Events")
        st.dataframe(bms_df)
    if not district_df.empty:
        st.markdown("### 🏙️ District Events")
        st.dataframe(district_df)
    if not ae_df.empty:
        st.markdown("### 🌐 AllEvents")
        st.dataframe(ae_df)

    consolidated = pd.concat([bms_df, district_df, ae_df], ignore_index=True)
    final_df = remove_duplicates(consolidated)

    st.markdown("## 📊 Consolidated Events")
    st.dataframe(final_df)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        bms_df.to_excel(writer, index=False, sheet_name="BookMyShow")
        district_df.to_excel(writer, index=False, sheet_name="District")
        ae_df.to_excel(writer, index=False, sheet_name="AllEvents")
        final_df.to_excel(writer, index=False, sheet_name="Consolidated")

    st.download_button("⬇️ Download All as Excel", data=output.getvalue(), file_name="pixie_events.xlsx")
