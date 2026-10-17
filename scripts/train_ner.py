"""Optional spaCy training; input JSONL uses text + entities[start,end,label]."""
import argparse,json,random
def train(path,out,epochs):
    import spacy
    from spacy.training import Example
    from spacy.util import minibatch,fix_random_seed
    fix_random_seed(42);nlp=spacy.blank('en');ner=nlp.add_pipe('ner')
    data=[json.loads(line) for line in open(path,encoding='utf-8') if line.strip()]
    for row in data:
        for start,end,label in row['entities']:ner.add_label(label)
    def examples():return [Example.from_dict(nlp.make_doc(r['text']),{'entities':r['entities']}) for r in data]
    optimizer=nlp.initialize(get_examples=examples)
    for epoch in range(epochs):
        random.shuffle(data);losses={}
        for batch in minibatch(examples(),size=8):nlp.update(batch,sgd=optimizer,drop=.2,losses=losses)
        print(epoch+1,losses)
    nlp.to_disk(out);print('Saved model; evaluate on institution-held-out records before production use.')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('jsonl');p.add_argument('--output',default='data/models/course-ner');p.add_argument('--epochs',type=int,default=20);a=p.parse_args();train(a.jsonl,a.output,a.epochs)
