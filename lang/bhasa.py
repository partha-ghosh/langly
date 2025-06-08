import dash
from dash import dcc, html, Input, Output, State, callback
import json
import uuid
import copy
from datetime import datetime, timedelta
import random
import base64
import re
from deep_translator import GoogleTranslator, MyMemoryTranslator, DeeplTranslator
import io
import functools
from gtts import gTTS

app = dash.Dash(__name__, external_stylesheets=['https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css'])
root_save_dir = '.'
# app.config['suppress_callback_exceptions'] = True

try:
    with open(f'{root_save_dir}/vocabulary.json', 'r') as f:
        data = json.load(f)
except FileNotFoundError:
    data = dict()

translator = dict(translator=None)

@functools.lru_cache(maxsize=512)
def translate(text):
    return translator['translator'].translate(text)

def save_data(data_to_save):
    with open(f'{root_save_dir}/vocabulary.json', 'w') as f:
        json.dump(data_to_save, f)

def create_word_buttons(sentence_idx, words, active_indices):
    buttons = []
    for i, word in enumerate(words):
        style = {'display': 'inline', 'margin': '2px', 'background-color': 'green' if i in active_indices else 'white'}
        button = html.Button(
            word,
            id={'type': 'word-btn', 'sentence_idx': sentence_idx, 'word_idx': i},
            style=style,
            className='btn btn-sm'
        )
        buttons.append(button)
    return buttons

def group_consecutive(indices):
    if not indices:
        return []
    groups = []
    current = [indices[0]]
    for idx in indices[1:]:
        if idx == current[-1] + 1:
            current.append(idx)
        else:
            groups.append(current)
            current = [idx]
    groups.append(current)
    return groups

# Add these new functions for spaced repetition
def get_due_subsentences(vocab_data, lang_key):
    today = datetime.today().date()
    due = []
    for subsentence, details in vocab_data.get(lang_key, {}).items():
        next_review = datetime.strptime(details.get('next_review', '2000-01-01'), '%Y-%m-%d').date()
        if next_review <= today:
            due.append((subsentence, details))
    random.shuffle(due)
    return due

def update_spaced_repetition(subsentence_details, rating):
    ratings = {'hard': 0.75, 'medium': 1.5, 'easy': 2.5}
    interval = subsentence_details.get('interval', 1)
    
    # Update interval based on rating
    new_interval = interval * ratings.get(rating, 1)
    subsentence_details['interval'] = new_interval
    
    # Calculate next review date
    next_review = datetime.today() + timedelta(days=int(new_interval))
    subsentence_details['next_review'] = next_review.strftime('%Y-%m-%d')
    
    # Update rating
    subsentence_details['rating'] = ratings.get(rating, 1)
    return subsentence_details

# Function to generate audio data URI
@functools.lru_cache(maxsize=4096)
def text_to_speech_uri(text, lang):
    tts = gTTS(text=text, lang=lang)
    # tts.save(f'{root_save_dir}/test.mp3')
    audio_buffer = io.BytesIO()
    tts.write_to_fp(audio_buffer)
    audio_buffer.seek(0)
    return f"data:audio/mpeg;base64,{base64.b64encode(audio_buffer.read()).decode()}"

options = [
    {'label': 'English', 'value': 'en'},
    {'label': 'German', 'value': 'de'},
    {'label': 'French', 'value': 'fr'},
    {'label': 'Italian', 'value': 'it'},
    {'label': 'Spanish', 'value': 'es'},
    {'label': 'Russian', 'value': 'ru'},
    {'label': 'Ukrainian', 'value': 'uk'},
    {'label': 'Polish', 'value': 'pl'}
]

app.layout = html.Div([
    html.Div([
        html.Div(
            dcc.Dropdown(
                id='lang1',
                options=options,
                value='en',
            ), className='col'
        ),
        html.Div(
            dcc.Dropdown(
                id='lang2',
                options=options,
                value='de',
            ), className='col'
        ),
    ], className='row'),
    dcc.Tabs(id='main-tabs', value='learn-tab', children=[
        dcc.Tab(label='Learn', value='learn-tab', children=[
            html.Div([
                dcc.Textarea(id='text-input', style={'width': '100%', 'height': 100}),
                html.Button('Process', id='process-btn', className='btn btn-primary mt-2 mb-2', style={'width': '100%'})
            ]),
            html.Div(id='sentences-container')
        ]),
        dcc.Tab(label='Recall', value='recall-tab', children=[
            html.Div(id='recall-container', className='mt-4', children=[
                html.Div(id='current-card'),
                html.Button('Show Answer', 
                          id='show-answer-btn', 
                          className='btn btn-info mt-3',
                          style={'display': 'none'}),
                html.Div(id='answer-container', className='mt-4'),
                html.Div(id='rating-buttons', style={'display': 'none'}, children=[
                    html.Button('Hard', id='hard-btn', className='btn btn-danger mr-2'),
                    html.Button('Medium', id='medium-btn', className='btn btn-warning mr-2'),
                    html.Button('Easy', id='easy-btn', className='btn btn-success'),
                ])
            ])
        ]),
        dcc.Tab(label='Vocabulary', value='vocab-tab', children=[
            html.Div([
                # dcc.Upload(
                #     id='upload-data',
                #     children=html.Span([
                #         'Drag and Drop or Select Vocabulary File',
                #     ]),
                #     className='btn btn-secondary mb-3',
                # ),
                # html.Button(
                #     "Download Vocabulary",
                #     id="download-btn",
                #     className='btn btn-success mb-3 ml-2'
                # ),
                dcc.Input(
                    id='search-input',
                    type='text',
                    placeholder='Search sentences...',
                    className='form-control mb-3',
                    style={'width': '300px'}
                ),
                html.Div(id='vocabulary-list')
            ], className='container mt-4')
        ])
    ]),
    dcc.Store(id='active-words', data={}),
    dcc.Store(id='sentences-store', data={}),
    dcc.Store(id='vocab-store', data=data),
    dcc.Store(id='session-store', data={
        'due_cards': [],
        'current_index': 0,
        'shown_answer': False
    }),
    # dcc.Download(id="download-vocabulary"),
    html.Audio(id='audio-player', autoPlay=False, controls=True)
])

@callback(
    Output('sentences-container', 'children'),
    Output('sentences-store', 'data'),
    Input('process-btn', 'n_clicks'),
    State('text-input', 'value'),
    State('lang1', 'value'),
    State('lang2', 'value'),
    prevent_initial_call=True
)
def process_text(n_clicks, text, lang1, lang2):
    if not text:
        return [], {}
    
    sentences = re.split(r'(?<=[.!?])\s+', text.strip()) #[s.strip() for s in text.split('.') if s.strip()]
    sentences_store = {}
    children = []

    # translator['translator'] = MyMemoryTranslator(source=[option for option in options if option['value']==lang1][0]['label'].lower(), target=[option for option in options if option['value']==lang2][0]['label'].lower()) #(source=lang1, target=lang2)
    translator['translator'] = DeeplTranslator(api_key="", source=lang1, target=lang2, use_free_api=True)

    for i, sent in enumerate(sentences):
        sent_id = str(uuid.uuid4())
        words = sent.split()
        translation = translator['translator'].translate(sent) # f"{sent} (translated to {lang2})"  # Mock translation
        sentences_store[sent_id] = {'sentence': sent, 'translation': translation, 'words': words}
        
        children.append(html.Div([
            html.Div(id={'type': 'words-container', 'sent_id': sent_id}, 
                     children=create_word_buttons(sent_id, words, [])),
            html.Div(translation, className='mt-2 mb-4'),
            html.Button('Read it', 
                          id={'type': 'read-it', 'data-text': translation.encode().hex(), 'data-lang': lang2},
                          className='btn btn-info btn-sm ml-2'),
            html.Div(id={'type': 'subs-container', 'sent_id': sent_id})
        ], className='mb-4 border p-3'))
    
    return children, sentences_store

@callback(
    Output({'type': 'subs-container', 'sent_id': dash.MATCH}, 'children'),
    Input('active-words', 'data'),
    State({'type': 'subs-container', 'sent_id': dash.MATCH}, 'id'),
    State('sentences-store', 'data'),
    State('lang1', 'value'),
    State('lang2', 'value'),
    prevent_initial_call=True
)
def update_subsentences(active_words, container_id, sentences_store, lang1, lang2):
    sent_id = container_id['sent_id']
    active = active_words.get(sent_id, [])
    groups = group_consecutive(active)
    
    subs = []
    sentence = sentences_store[sent_id]['sentence']
    words = sentences_store[sent_id]['words']
    
    for group in groups:
        if len(group) < 1:
            continue
        sub_words = [words[i] for i in range(group[0], group[-1]+1)]
        subsentence = ' '.join(sub_words)
        translation = translate(subsentence) #f"{subsentence} (translated)"

        subs.append(html.Div([
            html.Div([
                html.Strong(subsentence),
                html.Span(f" → {translation}", className='ml-2'),
                html.Button('Read it', 
                          id={'type': 'read-it', 'data-text': translation.encode().hex(), 'data-lang': lang2},
                          className='btn btn-info btn-sm ml-2'),
                html.Button('Add', 
                           id={'type': 'add-btn', 'sent_id': sent_id, 'start': group[0], 'end': group[-1]},
                           className='btn btn-success btn-sm ml-2'),
                html.Button('Remove', 
                           id={'type': 'remove-btn', 'sent_id': sent_id, 'start': group[0], 'end': group[-1]},
                           className='btn btn-danger btn-sm ml-2')
            ], className='mt-2 p-2 border')
        ]))
    
    return subs

@callback(
    Output('vocab-store', 'data'),
    Input({'type': 'add-btn', 'sent_id': dash.ALL, 'start': dash.ALL, 'end': dash.ALL}, 'n_clicks'),
    Input({'type': 'remove-btn', 'sent_id': dash.ALL, 'start': dash.ALL, 'end': dash.ALL}, 'n_clicks'),
    State('sentences-store', 'data'),
    State('vocab-store', 'data'),
    State('lang1', 'value'),
    State('lang2', 'value'),
    prevent_initial_call=True
)
def update_vocabulary(add_clicks, remove_clicks, sentences_store, vocab_data, lang1, lang2):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update

    if not ctx.triggered[0]['value']:
        return dash.no_update
    
    button_id = json.loads(ctx.triggered[0]['prop_id'].split('.')[0])
    sent_id = button_id['sent_id']
    start = button_id['start']
    end = button_id['end']

    sentence_data = sentences_store[sent_id]
    words = sentence_data['words']
    subsentence = ' '.join(words[start:end+1])
    lang_key = f"{lang1}2{lang2}"

    # Create copies to avoid modifying data in-place
    vocab_data = copy.deepcopy(vocab_data)
    
    # Initialize language entry if not exists
    if lang_key not in vocab_data:
        vocab_data[lang_key] = dict()

    if 'add-btn' in button_id['type']:
        vocab_data[lang_key].setdefault(subsentence, {
            'translation': translate(subsentence), #f"{subsentence} (translated)",
            'rating': 1,
            'examples': list()
        })
        vocab_data[lang_key][subsentence]['examples'].append((sentence_data['sentence'], sentence_data['translation']))
        vocab_data[lang_key][subsentence]['examples'] = vocab_data[lang_key][subsentence]['examples'][-100:]
    else:
        if len(vocab_data[lang_key][subsentence]['examples']) > 0:
            vocab_data[lang_key][subsentence]['examples'].pop(-1)
        if len(vocab_data[lang_key][subsentence]['examples']) == 0:
            vocab_data[lang_key].pop(subsentence)

    # Save the modified data
    save_data(vocab_data)
    return vocab_data

@callback(
    Output({'type': 'words-container', 'sent_id': dash.MATCH}, 'children'),
    Input('active-words', 'data'),
    State({'type': 'words-container', 'sent_id': dash.MATCH}, 'id'),
    State('sentences-store', 'data'),
    prevent_initial_call=True
)
def update_word_buttons(active_words, container_id, sentences_store):
    sent_id = container_id['sent_id']
    active_indices = active_words.get(sent_id, [])
    words = sentences_store[sent_id]['words']
    return create_word_buttons(sent_id, words, active_indices)

@callback(
    Output('active-words', 'data'),
    Input({'type': 'word-btn', 'sentence_idx': dash.ALL, 'word_idx': dash.ALL}, 'n_clicks'),
    State({'type': 'word-btn', 'sentence_idx': dash.ALL, 'word_idx': dash.ALL}, 'id'),
    State('active-words', 'data'),
    State('sentences-store', 'data'),
    prevent_initial_call=True
)
def update_active_words(_, btn_ids, active_words, sentences_store):
    ctx = dash.callback_context
    if not ctx.triggered:
        return active_words

    clicked_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if not ctx.triggered[0]['value']:
        return active_words

    clicked_data = json.loads(clicked_id)
    sent_id = clicked_data['sentence_idx']
    word_idx = clicked_data['word_idx']

    # Create a copy to avoid modifying the original data
    updated_active = dict(active_words)
    sentence_active = updated_active.get(sent_id, []).copy()

    if word_idx in sentence_active:
        sentence_active.remove(word_idx)
    else:
        sentence_active.append(word_idx)
        sentence_active.sort()

    updated_active[sent_id] = sentence_active
    return updated_active

# Add these new callbacks
@callback(
    Output('session-store', 'data'),
    Input('main-tabs', 'value'),  # Add id='recall-tab' to the Recall Tab
    State('vocab-store', 'data'),
    State('lang1', 'value'),
    State('lang2', 'value'),
    prevent_initial_call=True
)
def initialize_session(active_tab, vocab_data, lang1, lang2):
    if active_tab != 'recall-tab':
        return dash.no_update
    lang_key = f"{lang1}2{lang2}"
    due_cards = get_due_subsentences(vocab_data, lang_key)
    return {
        'due_cards': due_cards,
        'current_index': 0,
        'shown_answer': False
    }

@callback(
    Output('current-card', 'children'),
    Output('show-answer-btn', 'style'),
    Output('answer-container', 'children'),
    Output('rating-buttons', 'style'),
    Output('session-store', 'data', allow_duplicate=True),
    Output('vocab-store', 'data', allow_duplicate=True),
    Input('session-store', 'data'),
    Input('show-answer-btn', 'n_clicks'),
    Input('hard-btn', 'n_clicks'),
    Input('medium-btn', 'n_clicks'),
    Input('easy-btn', 'n_clicks'),
    State('vocab-store', 'data'),
    State('lang1', 'value'),
    State('lang2', 'value'),
    prevent_initial_call=True
)
def update_card(session_data, show_clicks, hard_clicks, medium_clicks, easy_clicks, vocab_data, lang1, lang2):
    ctx = dash.callback_context
    lang_key = f"{lang1}2{lang2}"
    current_index = session_data['current_index']
    due_cards = session_data['due_cards']
    
    if not due_cards:
        return html.H4("No cards due for review! 🎉"), {'display': 'none'}, [], {'display': 'none'}, session_data, vocab_data
    
    if current_index >= len(due_cards):
        return html.H4("Review complete! 🎉"), {'display': 'none'}, [], {'display': 'none'}, session_data, vocab_data
    
    # Get current card data
    subsentence, details = due_cards[current_index]

    # Handle button triggers
    if ctx.triggered:
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id == 'show-answer-btn':
            # Show answer
            related_sentences = vocab_data[lang_key][subsentence]['examples']
            related_sentences = random.sample(related_sentences, min(10, len(related_sentences)))
            
            example_items = []
            for s, t in related_sentences:
                example_items.append(html.Li([
                    html.Div([
                        s,
                        html.Button('Read it', 
                                  id={'type': 'read-it', 'data-text': s.encode().hex(), 'data-lang': lang1},    
                                  className='btn btn-info btn-sm ml-2')
                    ]),
                    html.Div([
                        t,
                        html.Button('Read it', 
                                  id={'type': 'read-it', 'data-text': t.encode().hex(), 'data-lang': lang2},    
                                  className='btn btn-info btn-sm ml-2')
                    ])
                ]))

            answer_content = [
                html.Div([
                    html.H5(f"Translation: {details['translation']}"), 
                    html.Button('Read it', 
                              className='btn btn-info btn-sm ml-2',
                              id={'type': 'read-it', 'data-text': details['translation'].encode().hex(), 'data-lang': lang2})
                ]),
                html.Hr(),
                html.H5("Example Sentences:"),
                html.Ul([html.Li(children=item) for item in example_items])
            ]
            return (
                html.H4(subsentence),
                {'display': 'none'},
                answer_content,
                {'display': 'block'},
                session_data,
                vocab_data
            )
        
        if trigger_id in ['hard-btn', 'medium-btn', 'easy-btn']:
            # Update spaced repetition parameters
            rating = trigger_id.split('-')[0]
            updated_details = update_spaced_repetition(details, rating)
            
            # Update vocabulary data
            vocab_data[lang_key][subsentence] = updated_details
            save_data(vocab_data)
            
            # Move to next card
            updated_session = session_data.copy()
            updated_session['current_index'] += 1
            updated_session['shown_answer'] = False
            
            # # Get next card
            if updated_session['current_index'] < len(updated_session['due_cards']):
                next_subsentence, _ = updated_session['due_cards'][updated_session['current_index']]
                return (
                    html.H4(next_subsentence),
                    {'display': 'block'},
                    [],
                    {'display': 'none'},
                    updated_session,  # Updated
                    vocab_data
                )
            else:
                return (
                    html.H4("Review complete! 🎉"),
                    {'display': 'none'},
                    [],
                    {'display': 'none'},
                    updated_session,  # Updated
                    vocab_data
                )
    
    # Default view (show question)
    return html.H4(subsentence), {'display': 'block'}, [], {'display': 'none'}, session_data, vocab_data

# Add this CSS to make the transitions smoother
# app.css.append_css({
#     'external_url': 'https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css'
# })

# Add vocabulary list and file handling callbacks
@callback(
    Output('vocabulary-list', 'children'),
    Input('search-input', 'value'),
    Input('vocab-store', 'data'),
    State('lang1', 'value'),
    State('lang2', 'value')
)
def update_vocabulary_list(search_text, vocab_data, lang1, lang2):
    lang_key = f"{lang1}2{lang2}"
    items = []
    
    # Get all sentences and filter by search text
    all_sentences = []
    for subsentence in vocab_data[lang_key]:
        examples = vocab_data[lang_key][subsentence]['examples']
        for sentence, translation in examples:
            all_sentences.append((sentence, translation))
    
    if search_text:
        search_lower = search_text.lower()
        filtered = [
            (s, t) for s, t in all_sentences
            if search_lower in s.lower() or search_lower in t.lower()
        ]
    else:
        filtered = all_sentences
    
    # Create list items
    for sentence, translation in filtered:
        item = html.Div([
            html.Div([
                html.Div([
                    sentence,
                    html.Button('Read it', 
                              className='btn btn-info btn-sm ml-2',
                              id={'type': 'read-it', 'data-text': sentence.encode().hex(), 'data-lang': lang1})
                ]),
                html.Div([
                    html.Strong(f'{translation}'),
                    html.Button('Read it', 
                              className='btn btn-info btn-sm ml-2',
                              id={'type': 'read-it', 'data-text': translation.encode().hex(), 'data-lang': lang2})
                ])
            ], className='p-3 border rounded mb-2',
               style={'backgroundColor': '#e9fce9'})
        ])
        items.append(item)
    
    if not items:
        return html.Div("No vocabulary found", className='text-muted')
    
    return items

# @callback(
#     Output("download-vocabulary", "data"),
#     Input("download-btn", "n_clicks"),
#     State('vocab-store', 'data'),
#     prevent_initial_call=True
# )
# def download_vocabulary(n_clicks, vocab_data):
#     return dict(base64=True, content=base64.b64encode(pickle.dumps(vocab_data)).decode(), filename="vocabulary.pkl")
#     # return dict(content=json.dumps(vocab_data, indent=2), filename="vocabulary.json")

# @callback(
#     Output('vocab-store', 'data', allow_duplicate=True),
#     Input('upload-data', 'contents'),
#     State('upload-data', 'filename'),
#     prevent_initial_call=True
# )
# def upload_vocabulary(contents, filename):
#     if contents is None:
#         return dash.no_update
    
#     content_type, content_string = contents.split(',')
#     decoded = base64.b64decode(content_string)
    
#     # new_data = json.loads(decoded.decode('utf-8'))
#     new_data = pickle.load(io.BytesIO(decoded))
#     save_data(new_data)
#     return new_data

# Text-to-speech callback
@callback(
    Output('audio-player', 'src'),
    Output('audio-player', 'autoPlay'),
    Input({'type': 'read-it', 'data-text': dash.ALL, 'data-lang': dash.ALL}, 'n_clicks'),
    prevent_initial_call=True
)
def text_to_speech(sentence_clicks):

    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update

    # Get the triggered element and its data-text attribute
    triggered_id = ctx.triggered[0]['prop_id'].split('.n_clicks')[0]

    # Handle clicks on "Read it" buttons
    if ctx.triggered[0]['value']:
        try:
            button_id = json.loads(triggered_id)
            if 'type' in button_id and button_id['type'] == 'read-it':
                text = button_id.get('data-text', '')
                lang = button_id.get('data-lang', 'de')

                if text:
                    return text_to_speech_uri(bytes.fromhex(text).decode(), lang), True
        except json.JSONDecodeError:
            pass
    
    # # Handle clicks in recall tab
    # elif triggered_id == 'current-card.children':
    #     if card_content and 'data-text' in card_content[1].props:
    #         text = card_content[1].props['data-text']
    #         return text_to_speech_uri(text, lang1), True
            
    # elif triggered_id == 'answer-container.children':
    #     if answer_content and 'data-text' in answer_content[0].children[0].props:
    #         text = answer_content[0].children[0].props['data-text']
    #         return text_to_speech_uri(text, lang2), True
            
    # # Handle clicks in vocabulary list
    # elif triggered_id == 'vocabulary-list.children':
    #     # This is more complex as there are multiple buttons
    #     # We'd need to track which button was clicked
    #     # For simplicity, we'll skip this for now
    #     pass

    return dash.no_update, dash.no_update


if __name__ == '__main__':
    app.run(host='0.0.0.0',debug=False, port=8050)