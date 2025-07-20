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
        for word_key in info['vocab_data'][lang_key]:
            examples = info['vocab_data'][lang_key][word_key]['examples']
            for sentence, translation in examples:
                all_sentences.setdefault(sentence, dict(translation=translation, usage=dict()))
                subsentence = vocab_data[lang_key][word_key]['subsentence']
                all_sentences[sentence]['usage'][subsentence] = vocab_data[lang_key][word_key]['translation']

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
                    Element('span', attrs=dict(class_="uk-label"), leaf=f"{word} → {meaning}")
                )
        
        for ri in range(idx+1, len(info['search_result_container'].children_order)):
            info['search_result_container'].update(
                Element('div'), index=ri
            )

            

def translate(text, source, target):
    info['translator'] = DeeplTranslator(api_key=info['deepl_api_key'], source=source, target=target, use_free_api=True)
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
    lang_key = f"{info['known_lang']}2{info['unknown_lang']}"

    info['vocab_data'].setdefault(lang_key, dict())


    if not info['vocab_data'][lang_key].get(f"{(subsentence,meaning)}", None):
        info['vocab_data'][lang_key][f"{(subsentence,meaning)}"] = dict(
            subsentence=subsentence,
            translation=meaning,
            rating=1,
            interval=1,
            examples=[]
        )
    info['vocab_data'][lang_key][f"{(subsentence,meaning)}"]['examples'].append(
        [info['sentences'][sent_idx], info['sentences'][sent_idx+1]] if (sent_idx % 2 == 0) else \
        [info['sentences'][sent_idx-1], info['sentences'][sent_idx]]
    )

    if len(info['vocab_data'][lang_key][f"{(subsentence,meaning)}"]['examples']) > 100:
        info['vocab_data'][lang_key][f"{(subsentence,meaning)}"]['examples'] = info['vocab_data'][lang_key][f"{(subsentence,meaning)}"]['examples'][-100:]

def pop_example(subsentence, meaning):
    lang_key = f"{info['known_lang']}2{info['unknown_lang']}"
    info['vocab_data'].setdefault(lang_key, dict())
    if info['vocab_data'][lang_key].get((subsentence,meaning), None):
        if len(info['vocab_data'][lang_key][f"{(subsentence,meaning)}"]['examples']) == 1:
            info['vocab_data'][lang_key].pop(f"{(subsentence,meaning)}")
        else:
            info['vocab_data'][lang_key][f"{(subsentence,meaning)}"]['examples'].pop(-1)

def delete_meaning(subsentence, meaning):
    lang_key = f"{info['known_lang']}2{info['unknown_lang']}"
    info['vocab_data'].setdefault(lang_key, dict())
    info['vocab_data'][lang_key].pop(f"{(subsentence,meaning)}", None)
    calc_dues()

def calc_dues():
    lang_key = f"{info['known_lang']}2{info['unknown_lang']}"
    info['dues'].setdefault(lang_key, [])
    info['dues'][lang_key].clear()

    today = datetime.today().date()
    for word_key, details in info['vocab_data'].get(lang_key, {}).items():
        next_review = datetime.strptime(details.get('next_review', '2000-01-01'), '%Y-%m-%d').date()
        if next_review <= today:
            info['dues'][lang_key].append(word_key)
    random.shuffle(info['dues'][lang_key])
    get_next_card()

def get_next_card():
    lang_key = f"{info['known_lang']}2{info['unknown_lang']}"
    if len(info['dues'][lang_key])==0:
        info['question_container'].update(Element('span', leaf='No more cards due for review! 🎉'), index=0)
        info['answer_container'].update(Element('span', leaf=''), index=0)
        return 0
    word_key = info['dues'][lang_key][0]
    subsentence = info['vocab_data'][lang_key][word_key]['subsentence']
    meaning = info['vocab_data'][lang_key][word_key]['translation']
    related_examples = random.sample(info['vocab_data'][lang_key][word_key]['examples'], min(10, len(info['vocab_data'][lang_key][word_key]['examples'])))

    if rand:=random.random() < 0.5:
        q = subsentence
        a = meaning
    else:
        q = meaning
        a = subsentence

    info['question_container'].update(Element('span', attrs=dict(class_="grid grid-cols-1 grid-rows-1 items-center")).add(
        Element('span', attrs=dict(class_="col-start-1 row-start-1 text-center")).add(
            Element('span', leaf=q + ' ')
        ).add(
            Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': text_to_speech, 'args': [q, info['unknown_lang'] if rand<0.5 else info['known_lang']]})!r})")).add(
                Element('uk-icon', attrs=dict(icon="volume-2"))
            )
        )
    ).add(
        Element('span', attrs=dict(class_="col-start-1 row-start-1 justify-self-end")).add(
            Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': delete_meaning, 'args': [subsentence, meaning]})!r})")).add(
                Element('uk-icon', attrs=dict(icon="trash-2"))
            )
        )
    ), index=0)
    info['answer_container'].update(
        Element('span').add(
            Element('span', leaf=a + ' ')
        ).add(
            Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': text_to_speech, 'args': [a, info['known_lang'] if rand<0.5 else info['unknown_lang']]})!r})")).add(
                Element('uk-icon', attrs=dict(icon="volume-2"))
            )
        ), index=0
    )

    examples = info['examples_container']
    idx = -1
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
    
    for ri in range(len(info['examples_container'].children_order)-1, idx, -1):
        info['examples_container'].remove(ri)   

def update_spaced_repetition(rating):
    lang_key = f"{info['known_lang']}2{info['unknown_lang']}"
    ratings = {'hard': 0.75, 'medium': 1.5, 'easy': 2.5}

    word_key = info['dues'][lang_key][0]
    interval = info['vocab_data'][lang_key][word_key]['interval']
    
    # Update interval based on rating
    new_interval = interval * ratings.get(rating, 1)
    info['vocab_data'][lang_key][word_key]['interval'] = new_interval
    
    # Calculate next review date
    next_review = datetime.today() + timedelta(days=int(new_interval))
    info['vocab_data'][lang_key][word_key]['next_review'] = next_review.strftime('%Y-%m-%d')
    
    # Update rating
    info['vocab_data'][lang_key][word_key]['rating'] = ratings.get(rating, 1)
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
            else:
                meaning = translate(subsentence, source=info['unknown_lang'], target=info['known_lang'])
            
            subsentence = re.sub(r'[^\w\s]', '', subsentence)
            meaning = re.sub(r'[^\w\s]', '', meaning)

            if si % 2 == 0:
                subsentences.append(subsentence)
                meanings.append(meaning)
            else:
                subsentences.append(meaning)
                meanings.append(subsentence)
    
    idx = -1
    for idx, (subsentence, meaning) in enumerate(zip(subsentences, meanings)):
        info['meanings_containers'][mci].update(
            Element('li').add(
                Element('div', attrs=dict(class_="pb-2"), leaf=subsentence + ' → '+ meaning)
            ).add(
                Element('div', attrs=dict(class_="flex justify-end gap-2")).add(
                    Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': text_to_speech, 'args': [subsentence, info['known_lang']]})!r})")).add(
                        Element('uk-icon', attrs=dict(icon="volume-2"))
                    )
                ).add(
                    Element('div', attrs=dict(class_="my-auto")).add(
                        Element('uk-icon', attrs=dict(icon="move-right"))
                    )
                ).add(
                    Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': text_to_speech, 'args': [meaning, info['unknown_lang']]})!r})")).add(
                        Element('uk-icon', attrs=dict(icon="volume-2"))
                    )
                ).add(
                    Element('div', attrs=dict(class_="my-auto")).add(
                        Element('uk-icon', attrs=dict(icon="ellipsis-vertical"))
                    )
                ).add(
                    Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': save_meaning, 'args': [subsentence, meaning, sent_idx]})!r})")).add(
                        Element('uk-icon', attrs=dict(icon="save"))
                    )
                ).add(
                    Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': pop_example, 'args': [subsentence, meaning]})!r})")).add(
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
    return groups[::-1]

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
            Element('div', attrs=dict(class_="uk-card uk-card-default uk-card-body mb-2")).add(
                word_container := Element('div', attrs=dict(class_="flex flex-wrap items-center gap-0.5 uk-btn-xs pb-2"))
            ).add(
                Element('div', attrs=dict(class_="flex justify-end gap-2")).add(
                    Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon self-end", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': text_to_speech, 'args': [sentence, info['known_lang']]})!r})")).add(
                        Element('uk-icon', attrs=dict(icon="volume-2"))
                    )
                )
            )
        ).add(
            Element('div', attrs=dict(class_="uk-card uk-card-secondary uk-card-body mb-2")).add(
                translated_word_container := Element('div', attrs=dict(class_="flex flex-wrap items-center gap-0.5 uk-btn-xs pb-2"))
            ).add(
                Element('div', attrs=dict(class_="flex justify-end gap-2")).add(
                    Element('a', attrs=dict(class_="uk-btn uk-btn-default uk-btn-sm uk-btn-icon self-end", onclick=f"socket.emit('exec_py_serialized', {serialize_to_base64({'fn': text_to_speech, 'args': [translation, info['unknown_lang']]})!r})")).add(
                        Element('uk-icon', attrs=dict(icon="volume-2"))
                    )
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
                Element('a', attrs=dict(class_="uk-btn", onclick=f"this.classList.toggle('uk-btn-primary'); socket.emit('exec_py_serialized', {serialize_to_base64({'fn': modify_selected_indices, 'args': [2*sent_idx+1, word_idx]})!r})"), leaf=word)
            )
        info['learn_container'].add(card)


def known_lang(lang):
    config = load_json(f'{root_save_dir}/config.json')
    config['known_lang'] = lang
    save_json(f'{root_save_dir}/config.json', config)
    info['known_lang'] = info['supported_langs'][lang]

def unknown_lang(lang):
    config = load_json(f'{root_save_dir}/config.json')
    config['unknown_lang'] = lang
    save_json(f'{root_save_dir}/config.json', config)
    info['unknown_lang'] = info['supported_langs'][lang]

def save_deepl_api_key(api_key):
    config = load_json(f'{root_save_dir}/config.json')
    config['deepl_api_key'] = api_key
    save_json(f'{root_save_dir}/config.json', config)
    info['deepl_api_key'] = api_key  


@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    config = load_json(f'{root_save_dir}/config.json')
    
    known_lang = config.get('known_lang', 'English')
    unknown_lang = config.get('unknown_lang', 'German')
    deepl_api_key = config.get('deepl_api_key', '')

    info['known_lang'] = info['supported_langs'][known_lang]
    info['unknown_lang'] = info['supported_langs'][unknown_lang]
    info['deepl_api_key'] = deepl_api_key    


    for container, id, label, default_lang in [('known-lang-container', 'known_lang', "Language you know", known_lang), ('unknown-lang-container', 'unknown_lang', "Language to learn", unknown_lang)]:
        div = Element('span')
        div.add(
            Element('label', attrs=dict(class_="uk-form-label"), leaf=label)
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