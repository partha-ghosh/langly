from flask_socketio import emit
import uuid

class Element:
    action_hooks = dict()

    def __init__(self, type, attrs=dict(), leaf=None):
        self.type = type
        self.attrs = attrs
        self.children_order=['val'] if leaf else []
        self.children=dict(val=leaf) if leaf else dict()
        self.key = uuid.uuid4().hex

    def add(self, ele, index=None, after=None):
        # use either index or after (by key)
        self.children[ele.key] = ele
        if ((index is None) and (after is None)):
            index = len(self.children_order)
        elif (index is None):
            index = self.children_order.index(after)+1

        self.children_order.insert(index, ele.key)
        
        if index:
            sibling_id = self.children_order[index-1]
            parent_id = None
        else:
            parent_id = self.key
            sibling_id = None
            
        emit('exec_js', "insertElement({}, {}, {!r})".format(('"'+parent_id+'"') if parent_id else 'null', ('"'+sibling_id+'"') if sibling_id else 'null', self.html(index)))
        return self

    def update(self, ele, index=None, key=None):
        # use either index or after (by key)
        assert ((index is not None) or (key is not None)), 'index and key both cannot be None'
        try:
            if index is not None:
                key = self.children_order[index]
            else:
                index = self.children_order.index(key)

            self.children[key] = ele
            ele.key = key

            emit('exec_js', "updateElement({}, {!r})".format('"'+key+'"', self.html(index)))
            return self
        except:
            try:
                return self.add(ele, index)
            except:
                raise 'Updating failed, so tried to add but it also failed!'

    def remove(self, index=-1, key=None):
        # use either index or key
        if key is None:
            key = self.children_order.pop(index)
        else:
            self.children_order.pop(self.children_order.index(key))
        self.children.pop(key)

        emit('exec_js', f"removeElement({key!r})")
        return self

    def clear(self):
        for i in range(len(self.children_order)-1,-1,-1):
            self.remove(index=i)

    def html(self, index=None):
        if index is not None:
            children_order = self.children_order[index: index+1]
        else:
            children_order = self.children_order

        if 'val' in children_order:
            return f'''<{self.type} {" ".join([f'{attr.replace("__", "-").replace("_", "")}="{val}"' for attr, val in self.attrs.items()])} id="{self.key}">{self.children['val']}</{self.type}>'''
        return (f'''<{self.type} {" ".join([f'{attr.replace("__", "-").replace("_", "")}="{val}"' for attr, val in self.attrs.items()])} id="{self.key}">''' if index is None else '')\
                + f'''{"".join([self.children[key].html() for key in children_order])}''' + \
                (f'''</{self.type}>''' if index is None else '')
        
    def action_hook(self, fn):
        self.action_hooks[self.key] = fn
