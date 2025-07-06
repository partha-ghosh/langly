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

# def build_page():
#     container = Element('div', attrs=dict(class_="uk-container uk-container-expand"))
#     grid_cols_2 = Element('div', attrs=dict(class_="grid grid-cols-2 gap-3 py-3"))
#     container.add(grid_cols_2)
    
#     div1 = Element('div')
#     grid_cols_2.add(div1)
#     select = Element('uk-select', attrs=dict(cls__custom="button: uk-input-fake justify-between w-full; dropdown: w-full", icon=""))
#     div1.add(Element('label', attrs=dict(class_="uk-form-label", for_=select.key), leaf="Language you know"), index=0)
#     div1.add(select)
#     iselect = Element('select', attrs=dict(hidden=""))
#     select.add(iselect)
#     iselect.add(Element('option', attrs=dict(value='en', selected=''), leaf='English'))
#     iselect.add(Element('option', attrs=dict(value='de'), leaf='German'))

#     div2 = Element('div')
#     grid_cols_2.add(div2)
#     select = Element('uk-select', attrs=dict(cls__custom="button: uk-input-fake justify-between w-full; dropdown: w-full", icon=""))
#     div2.add(Element('label', attrs=dict(class_="uk-form-label", for_=select.key), leaf="Language to learn"), index=0)
#     div2.add(select)
#     iselect = Element('select', attrs=dict(hidden=""))
#     select.add(iselect)
#     iselect.add(Element('option', attrs=dict(value='en'), leaf='English'))
#     iselect.add(Element('option', attrs=dict(value='de', selected=''), leaf='German'))


#     container.add(ul:=Element('ul', attrs=dict(class_="uk-tab-alt uk-margin", data__uk__switcher="animation: uk-anmt-fade")))
#     ul.add(
#         Element('li', attrs=dict(class_="uk-active")).add(
#             Element('a', attrs=dict(href="#")).add(
#                 Element('uk-icon', attrs=dict(icon='graduation-cap', class_='pe-1'))
#             ).add(
#                 Element('span', leaf=" Learn")
#             )
#         )
#     ).add(
#         Element('li').add(
#             Element('a', attrs=dict(href="#")).add(
#                 Element('uk-icon', attrs=dict(icon='brain', class_='pe-1'))
#             ).add(
#                 Element('span', leaf=" Recall")
#             )
#         )
#     ).add(
#         Element('li').add(
#             Element('a', attrs=dict(href="#")).add(
#                 Element('uk-icon', attrs=dict(icon='book-a', class_='pe-1'))
#             ).add(
#                 Element('span', leaf=" Vocabulary")
#             )
#         )
#     )

#     container.add(
#         Element('ul', attrs=dict(class_="uk-switcher mt-3")).add(
#             Element('li').add(
#                 Element('textarea', attrs=dict(class_="uk-textarea", rows='4', placeholde='Type your text ...'))
#             ).add(
#                 Element('div', attrs=dict(class_="flex justify-center py-3")).add(
#                     Element('a', attrs=dict(class_="uk-btn uk-btn-default", href="#"), leaf="Submit")
#                 )
#             )
#         ).add(
#             Element('li').add(
#                 # Element('h2', attrs=dict(class_="text-center"), leaf="No cards due for review! 🎉")
#                 Element('div').add(
#                     Element('div', attrs=dict(class_="uk-card uk-card-default uk-card-body my-3 text-center"), leaf="...")
#                 ).add(
#                     Element('div', attrs=dict(class_="flex justify-center py-3")).add(
#                         Element('button', attrs=dict(class_="uk-btn uk-btn-default", type_="button", data__uk__toggle=f"target: .answer-toggle; animation: uk-anmt-fade"), leaf="Show Answer")
#                     )
#                 ).add(
#                     Element('div', attrs=dict(class_="uk-card uk-card-default uk-card-body my-3 text-center answer-toggle"), leaf="...")
#                 ).add(
#                     answer := Element('div', attrs=dict(class_="uk-card uk-card-default uk-card-body my-3 text-center answer-toggle", hidden=""), leaf="What's up?")
#                 ).add(
#                     Element('div', attrs=dict(class_="flex justify-center gap-3 py-3")).add(
#                         Element('a', attrs=dict(class_="uk-btn uk-btn-secondary", href="#"), leaf="Easy")
#                     ).add(
#                         Element('a', attrs=dict(class_="uk-btn uk-btn-primary", href="#"), leaf="Medium")
#                     ).add(
#                         Element('a', attrs=dict(class_="uk-btn uk-btn-destructive", href="#"), leaf="Hard")
#                     )
#                 ).add(
#                     Element('div', attrs=dict(class_="answer-toggle", hidden="")).add(
#                         Element('div', attrs=dict(class_="py-3")).add(
#                             Element('h3', attrs=dict(class_="uk-card-title mb-1"), leaf="Examples")
#                         ).add(
#                             Element('hr', attrs=dict(class_="uk-hr"))
#                         )
#                     ).add(
#                         examples := Element('ul', attrs=dict(class_="uk-list uk-list-divider"))
#                     )
#                 )
#             )
#         ).add(
#             Element('li').add(
#                 vocab_list := Element('div', attrs=dict(class_="space-y-2")).add(
#                     Element('input', attrs=dict(class_="uk-input", type_="text", placeholder="Search"))
#                 )
#             )
#         )
#     )


#     body = Element('body')
#     body.add(container)

# div = Element('div')
# s = Element('select')
# div.add(s, 0)
# s.add(Element('option', leaf='Option 1'))
# s.add(Element('option', leaf='Option 2'))
# s.remove()
# s.add(Element('option', leaf='Option 3'))


# div = Element('div')
# select = Element('uk-select', attrs=dict(id_="known-lang", cls__custom="button: uk-input-fake justify-between w-full; dropdown: w-full", icon=""))
# div.add(Element('label', attrs=dict(class_="uk-form-label", for_=select.key), leaf="Language you know"), 0)
# div.add(select)
# iselect = Element('select', attrs=dict(hidden=""))
# select.add(iselect)
# iselect.add(Element('option', attrs=dict(value='en', selected=''), leaf='English'))
# es = Element('option', attrs=dict(value='es', selected=''), leaf='Spanish')
# # es.remove(-1)
# # es.add(Element('div'))
# iselect.add(es)
# iselect.add(Element('option', attrs=dict(value='de', selected=''), leaf='German'))
# iselect.remove(ele=es)

# print(div.html())

# from datetime import datetime, timedelta
# import random

# selected_word_indices = [[0,1,2, 4,5,6,7,8, 10], [2,3,7,8,9]]


# # Add these new functions for spaced repetition


# old_group = group_consecutive(selected_word_indices[0])
# print(old_group)
# selected_word_indices[0].pop(2)
# new_group = group_consecutive(selected_word_indices[0])
# print(new_group)
# print(set(new_group)-set(old_group))
# print(set(old_group)-set(new_group))