from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from utils import Element
import re
from deep_translator import GoogleTranslator, MyMemoryTranslator, DeeplTranslator
from gtts import gTTS
import io
import base64
import pickle
import time
import json
from datetime import datetime, timedelta
import random
import atexit
import re
import math
from api_keys import DEEPL_API_KEY

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app)

def load_json(path_to_json):
    try:
        with open(path_to_json, 'r') as f:
            return json.load(f) 
    except:
        save_json(path_to_json, dict())
        return load_json(path_to_json)

def save_json(path_to_json, data):
    with open(path_to_json, 'w') as f:
        json.dump(data, f)

root_save_dir = '.'
try:
    vocab_data = load_json(f'{root_save_dir}/vocabulary.json')
except FileNotFoundError:
    vocab_data = dict()

info = dict(
    supported_langs=dict(
        English='en',
        German='de',
        French='fr',
        Spanish='es',
        Italian='it',
        Russian='ru',
        Ukranian='uk',
        Polish='pl'
    ),
    known_lang='en',
    unknown_lang='de',
    vocab_data = vocab_data,
    dues = dict(),
    translation_cache = dict(),
    tts_cache = dict(),
    translator = None,
    sentences = [],
    words = [],
    selected_indices = [],
    lock = dict(),
    next_fn = dict(),

    meanings_containers = [],
    learn_container = [learn_container := Element('div'), setattr(learn_container, 'key', 'learn-container')][0],
    question_container = [question_container := Element('span'), setattr(question_container, 'key', 'question')][0],
    answer_container = [answer_container := Element('span'), setattr(answer_container, 'key', 'answer')][0],
    examples_container = [examples_container := Element('div', attrs=dict(class_="uk-list uk-list-divider")), setattr(examples_container, 'key', 'examples')][0],
    search_result_container = [search_result_container := Element('div', attrs=dict(class_="space-y-2")), setattr(search_result_container, 'key', 'search_results')][0],

)


def serialize_to_base64(obj):
    """Serialize any Python object to a Base64 string."""
    pickled_data = pickle.dumps(obj)
    base64_encoded = base64.b64encode(pickled_data)
    return base64_encoded.decode('utf-8')

def deserialize_from_base64(base64_str):
    """Deserialize a Base64 string back to the original Python object."""
    base64_bytes = base64_str.encode('utf-8')
    pickled_data = base64.b64decode(base64_bytes)
    return pickle.loads(pickled_data)

def save_vocab():
    save_json(f'{root_save_dir}/vocabulary.json', info['vocab_data'])

atexit.register(save_vocab)

def update_vocab_list(search_string):
    if (not search_string and len(info['search_result_container'].children_order) == 0) \
        or (search_string and len(info['search_result_container'].children_order) > 0):

        lang_key = f"{info['known_lang']}2{info['unknown_lang']}"
        info['vocab_data'].setdefault(lang_key, dict())

        # Get all sentences and filter by search text
        all_sentences = dict()
        for subsentence in info['vocab_data'][lang_key]:
            subsentence = re.sub(r'[^a-zA-Z0-9 ]', '', subsentence)
            examples = info['vocab_data'][lang_key][subsentence]['examples']
            for sentence, translation in examples:
                all_sentences.setdefault(sentence, dict(translation=translation, usage=dict()))
                all_sentences[sentence]['usage'][subsentence] = vocab_data[lang_key][subsentence]['translation']

        if search_string:
            search_lower = search_string.lower()
            filtered = [
                item for item in all_sentences.items() if search_lower in str(item).lower()
            ]
        else:
            filtered = list(all_sentences.items())
        
        idx = -1
        for idx, (sentence, others) in enumerate(filtered):
            translation = others['translation']
            usage = others['usage']

            info['search_result_container'].update(
                search_result := Element('div', attrs=dict(class_="uk-card uk-card-default uk-card-body")).add(
                    Element('p', leaf=sentence)
                ).add(
                    Element('p', attrs=dict(class_="pb-2 text-muted-foreground"), leaf=translation)
                ), index=idx
            )

            for word, meaning in usage.items():
                search_result.add(
                    Element('span', attrs=dict(class_="uk-label"), leaf=f"{word} -> {meaning}")
                )
        
        for ri in range(idx+1, len(info['search_result_container'].children_order)):
            info['search_result_container'].update(
                Element('div'), index=ri
            )

            

def translate(text, source, target):
    info['translator'] = DeeplTranslator(api_key=DEEPL_API_KEY, source=source, target=target, use_free_api=True)
    translation = info['translation_cache'].get(text, None)

    if translation is None:
        translation = info['translator'].translate(text)
        info['translation_cache'][text] = translation

    return translation

def text_to_speech(text, lang):
    data = info['tts_cache'].get(text, None)

    if data is None:
        tts = gTTS(text=text, lang=lang)
        # tts.save(f'{root_save_dir}/test.mp3')
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        data = f"data:audio/mpeg;base64,{base64.b64encode(audio_buffer.read()).decode()}"
        info['tts_cache'][text] = data

    emit('play', data)
    # return data

def save_meaning(subsentence, meaning, sent_idx):
    subsentence = re.sub(r'[^a-zA-Z0-9 ]', '', subsentence)

    lang_key = f"{info['known_lang']}2{info['unknown_lang']}"

    info['vocab_data'].setdefault(lang_key, dict())


    if not info['vocab_data'][lang_key].get(subsentence, None):
        info['vocab_data'][lang_key][subsentence] = dict(
            translation=meaning,
            rating=1,
            interval=1,
            examples=[]
        )
    info['vocab_data'][lang_key][subsentence]['examples'].append(
        [info['sentences'][sent_idx], info['sentences'][sent_idx+1]] if (sent_idx % 2 == 0) else \
        [info['sentences'][sent_idx-1], info['sentences'][sent_idx]]
    )

    if len(info['vocab_data'][lang_key][subsentence]['examples']) > 100:
        info['vocab_data'][lang_key][subsentence]['examples'] = info['vocab_data'][lang_key][subsentence]['examples'][-100:]

def delete_meaning(subsentence, sent_idx):
    subsentence = re.sub(r'[^a-zA-Z0-9 ]', '', subsentence)
    
    if sent_idx % 2 == 0: 
        lang_key = f"{info['known_lang']}2{info['unknown_lang']}"
    else:
        lang_key = f"{info['unknown_lang']}2{info['known_lang']}"

    info['vocab_data'].setdefault(lang_key, dict())
    if info['vocab_data'][lang_key].get(subsentence, None):
        if len(info['vocab_data'][lang_key][subsentence]['examples']) == 1:
            info['vocab_data'][lang_key].pop(subsentence)
        else:
            info['vocab_data'][lang_key][subsentence]['examples'].pop(-1)

def calc_dues():
    lang_key = f"{info['known_lang']}2{info['unknown_lang']}"
    info['dues'].setdefault(lang_key, [])
    
    if len(info['dues'][lang_key]) == 0:
        today = datetime.today().date()
        for subsentence, details in info['vocab_data'].get(lang_key, {}).items():
            next_review = datetime.strptime(details.get('next_review', '2000-01-01'), '%Y-%m-%d').date()
            if next_review <= today:
                info['dues'][lang_key].append(subsentence)
        random.shuffle(info['dues'][lang_key])

        get_next_card()

def get_next_card():
    lang_key = f"{info['known_lang']}2{info['unknown_lang']}"
    if len(info['dues'][lang_key])==0:
        info['question_container'].update(Element('span', leaf='No more cards due for review! 🎉'), index=0)
        info['answer_container'].update(Element('span', leaf=''), index=0)
        return 0
    subsentence = info['dues'][lang_key][0]
    meaning = info['vocab_data'][lang_key][subsentence]['translation']
    related_examples = random.sample(info['vocab_data'][lang_key][subsentence]['examples'], min(10, len(info['vocab_data'][lang_key][subsentence]['examples'])))

    info['question_container'].update(Element('span', leaf=subsentence), index=0)
    info['answer_container'].update(
        Element('span').add(
            Element('span', leaf=meaning + ' ')
        ).add(
            Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': text_to_speech, 'args': [meaning, info['unknown_lang']]})!r})")).add(
                Element('uk-icon', attrs=dict(icon="volume-2"))
            )
        ), index=0
    )

    examples = info['examples_container']
    for idx, (sentence, translation) in enumerate(related_examples):
        examples.update(
            Element('li').add(
                Element('p', leaf=sentence)
            ).add(
                Element('div').add(
                    Element('span', attrs=dict(class_="py-1 text-muted-foreground"), leaf=translation + ' ')
                ).add(
                    Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': text_to_speech, 'args': [translation, info['unknown_lang']]})!r})")).add(
                        Element('uk-icon', attrs=dict(icon="volume-2"))
                    )
                )
            ), index=idx
        )

def update_spaced_repetition(rating):
    lang_key = f"{info['known_lang']}2{info['unknown_lang']}"
    ratings = {'hard': 0.75, 'medium': 1.5, 'easy': 2.5}

    subsentence = info['dues'][lang_key][0]
    interval = info['vocab_data'][lang_key][subsentence]['interval']
    
    # Update interval based on rating
    new_interval = interval * ratings.get(rating, 1)
    info['vocab_data'][lang_key][subsentence]['interval'] = new_interval
    
    # Calculate next review date
    next_review = datetime.today() + timedelta(days=int(new_interval))
    info['vocab_data'][lang_key][subsentence]['next_review'] = next_review.strftime('%Y-%m-%d')
    
    # Update rating
    info['vocab_data'][lang_key][subsentence]['rating'] = ratings.get(rating, 1)
    info['dues'][lang_key].pop(0)

    get_next_card()

def modify_selected_indices(sent_idx, word_idx):
    if word_idx in info['selected_indices'][sent_idx]:
        info['selected_indices'][sent_idx].remove(word_idx)
    else:
        info['selected_indices'][sent_idx].append(word_idx)

    run_recent(info['lock'], info['next_fn'], (modify_selected_indices2, sent_idx), {'fn': modify_selected_indices2, 'args': (sent_idx, )})

def modify_selected_indices2(sent_idx):  
    # info['meanings_containers'][sent_idx].clear()
    subsentences = []
    meanings = []
    
    mci = int(math.floor(sent_idx/2))
    for si in ([sent_idx, sent_idx+1] if (sent_idx % 2 == 0) else [sent_idx-1, sent_idx]):
        new_groups = group_consecutive(info['selected_indices'][si])
        for word_indices in new_groups:
            subsentence = " ".join(info['words'][si][idx] for idx in word_indices)
            if si % 2 == 0:
                meaning = translate(subsentence, source=info['known_lang'], target=info['unknown_lang'])
                subsentences.append(subsentence)
                meanings.append(meaning)
            else:
                meaning = translate(subsentence, source=info['unknown_lang'], target=info['known_lang'])
                subsentences.append(meaning)
                meanings.append(subsentence)
    
    idx = -1
    for idx, (subsentence, meaning) in enumerate(zip(subsentences, meanings)):
        info['meanings_containers'][mci].update(
            Element('li').add(
                Element('div', attrs=dict(class_="pb-2"), leaf=subsentence + ' → '+ meaning)
            ).add(
                Element('div', attrs=dict(class_="flex justify-end gap-2")).add(
                    Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': text_to_speech, 'args': [meaning  if (sent_idx%2==0) else subsentence, info['unknown_lang']]})!r})")).add(
                        Element('uk-icon', attrs=dict(icon="volume-2"))
                    )
                ).add(
                    Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': save_meaning, 'args': [subsentence, meaning, sent_idx]})!r})")).add(
                        Element('uk-icon', attrs=dict(icon="save"))
                    )
                ).add(
                    Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': delete_meaning, 'args': [subsentence, sent_idx]})!r})")).add(
                        Element('uk-icon', attrs=dict(icon="trash-2"))
                    )
                )
            ), index=idx
        )
    
    for ri in range(len(info['meanings_containers'][mci].children_order)-1, idx, -1):
        info['meanings_containers'][mci].remove(ri)        


def group_consecutive(indices):
    if not indices:
        return []
    indices.sort()
    groups = []
    current = [indices[0]]
    for idx in indices[1:]:
        if idx == current[-1] + 1:
            current.append(idx)
        else:
            groups.append(tuple(current))
            current = [idx]
    groups.append(tuple(current))
    return groups

def process_text(text):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    info['sentences'].clear()
    info['learn_container'].clear()
    info['meanings_containers'].clear()
    info['words'].clear()
    
    info['selected_indices'] = [[] for _ in range(2*len(sentences))]
    
    for sent_idx, sentence in enumerate(sentences):
        translation = translate(sentence, source=info['known_lang'], target=info['unknown_lang'])
        info['sentences'].extend([sentence, translation])

        [card := Element('div', attrs=dict(class_="uk-card uk-card-default uk-card-body")).add(
            word_container := Element('div', attrs=dict(class_="flex flex-wrap items-center gap-0.5 uk-btn-xs pb-2"))
        ).add(
            Element('div', attrs=dict(class_="flex justify-between gap-2 pb-2")).add(
                translated_word_container := Element('div', attrs=dict(class_="flex flex-wrap items-center gap-0.5 uk-btn-xs pb-2"))
                # Element('div', attrs=dict(class_="py-1 text-muted-foreground"), leaf=translation)
            ).add(
                Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon self-end", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': text_to_speech, 'args': [translation, info['unknown_lang']]})!r})")).add(
                    Element('uk-icon', attrs=dict(icon="volume-2"))
                )
            )
        ).add(
            meanings_container := Element('ul', attrs=dict(class_="uk-list uk-list-striped"))
        )]
        
        info['meanings_containers'].append(meanings_container)
        words = sentence.split()
        info['words'].append(words)

        for word_idx, word in enumerate(words):
            word_container.add(
                Element('a', attrs=dict(class_="uk-btn", onclick=f"this.classList.toggle('uk-btn-primary'); socket.emit('exec_py_serialized', {serialize_to_base64({'fn': modify_selected_indices, 'args': [2*sent_idx, word_idx]})!r})"), leaf=word)
            )
            
        translated_words = translation.split()
        info['words'].append(translated_words)

        for word_idx, word in enumerate(translated_words):
            translated_word_container.add(
                Element('a', attrs=dict(class_="uk-btn", onclick=f"this.classList.toggle('uk-btn-secondary'); socket.emit('exec_py_serialized', {serialize_to_base64({'fn': modify_selected_indices, 'args': [2*sent_idx+1, word_idx]})!r})"), leaf=word)
            )
        info['learn_container'].add(card)


def known_lang(lang):
    config = load_json(f'{root_save_dir}/config.json')
    config['known_lang'] = lang
    save_json(f'{root_save_dir}/config.json', config)
    info['known_lang'] = info['supported_langs'][lang]
    calc_dues()

def unknown_lang(lang):
    config = load_json(f'{root_save_dir}/config.json')
    config['unknown_lang'] = lang
    save_json(f'{root_save_dir}/config.json', config)
    info['unknown_lang'] = info['supported_langs'][lang]
    calc_dues()



@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    config = load_json(f'{root_save_dir}/config.json')
    
    known_lang = config.get('known_lang', 'English')
    unknown_lang = config.get('unknown_lang', 'German')

    info['known_lang'] = info['supported_langs'][known_lang]
    info['unknown_lang'] = info['supported_langs'][unknown_lang]

    for container, id, default_lang in [('known-lang-container', 'known_lang', known_lang), ('unknown-lang-container', 'unknown_lang', unknown_lang)]:
        div = Element('span')
        div.add(
            Element('label', attrs=dict(class_="uk-form-label"), leaf="Language you know")
        ).add(
            Element('div', attrs=dict(class_="uk-form-controls")).add(
                uk_sel := Element('uk-select', attrs=dict(value=default_lang, cls__custom="button: uk-input-fake justify-between w-full; dropdown: w-full", icon="", onclick="socket.emit('exec_py', {{fn: '{id}', args: [document.getElementById('{id}').selected.value]}})".format(id=id))).add(
                    se := Element('select', attrs=dict(hidden=""))
                )
            )
        )

        uk_sel.key = id

        for lang in info['supported_langs']:
            se.add(Element('option', leaf=lang))
        
        parent = Element('div')
        parent.key=container
        parent.update(div, index=0)

    print('Client connected!')

@socketio.on('exec_py')
def handle_exec_py(data):

    if data['fn'] == 'process_text':
        run_recent(info['lock'], info['next_fn'], (globals()[data['fn']], data['args']), {'fn': globals()[data['fn']], 'args': data['args']})
    else:
        return globals()[data['fn']](*data['args'])
    # emit('resp', {'message': '<h2>Hello</h2>'})

@socketio.on('exec_py_serialized')
def handle_exec_py_serialized(data):
    data = deserialize_from_base64(data)
    return data['fn'](*data['args'])

def run_recent(lock, next, identifier, fn_data):
    identifier = serialize_to_base64(identifier)

    next[identifier] = fn_data

    while lock.get(identifier, None):
        time.sleep(0.01)
    
    lock[identifier] = True
    fn = fn_data['fn']
    args = fn_data.get('args', tuple())
    kwargs = fn_data.get('kwargs', dict())
    x = fn(*args, **kwargs)  
    lock[identifier] = False    
    return x

if __name__ == '__main__':
    socketio.run(app, debug=False, use_reloader=False)