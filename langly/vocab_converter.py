import json
import hashlib

with open('vocabulary3.json', 'r') as f:
    vocab = json.load(f) 

vocab['examples'] = dict()

for lang_key in vocab:
    if '2' in lang_key:
        for word_key in vocab[lang_key]:
            examples = vocab[lang_key][word_key].pop('examples')
            vocab[lang_key][word_key].setdefault('example_ids', [])

            for example in examples:
                example_id = hashlib.md5(str(example).encode('UTF-8')).hexdigest()
                vocab['examples'][example_id] = example
                if example_id not in vocab[lang_key][word_key]['example_ids']:
                    vocab[lang_key][word_key]['example_ids'].append(example_id)

with open('vocabulary.json', 'w') as f:
    json.dump(vocab, f)
