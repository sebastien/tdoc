" tdoc.vim

if exists("b:current_syntax")
  finish
endif

" NOTES: Needs to be escape:
" - chars: \d \w …
" - +: \+, but not *,
"

syn match   tdocLine "^\s*" nextGroup=tdocHTML,tdocHTMLStruct,tdocSingLeNode,tdocAttribute
syn keyword tdocHTML contained h1 h2 h3 h4 h5 h6 h8 ul li pre code
syn keyword tdocHTMLStruct contained main body html title section nav header
syn match   tdocNodeName contained "\w\+"
syn match   tdocNodeType contained "|\w\+"
syn match   tdocAttribute contained "@\w\+\s*" nextGroup=tdocAttributeValue
syn match   tdocAttributeValue contained ".\+$"

" SEE <https://github.com/posva/vim-vue/blob/master/syntax/vue.vim>
let s:embedded = [ 'javascript', 'python', 'markdown' ]
for s:lang in s:embedded
	execute 'syntax include @' . s:lang . ' syntax/' . s:lang . '.vim'
	" eg: syn region tdocJavaScript1 start="|javascript$" end="^[^\t][^t]\+$" contains=@javascript
	execute 'syn region tdoc_lang_' . s:lang . '_L0  start="^t\w*|' . s:lang . '$" end="^[^\t]\+$" contains=@' . s:lang
	execute 'syn region tdoc_lang_' . s:lang . '_L1  start="^\t\w*|' . s:lang . '$" end="^[^\t][^\t]\+$" contains=@' . s:lang
	execute 'syn region tdoc_lang_' . s:lang . '_L2  start="^\t\tw*|' . s:lang . '$" end="^[^\t][^\t][^\t]\+$" contains=@' . s:lang
	execute 'hi def link tdoc_lang_' . s:lang . '_L0 PreProc'
	execute 'hi def link tdoc_lang_' . s:lang . '_L1 PreProc'
	execute 'hi def link tdoc_lang_' . s:lang . '_L2 PreProc'
endfor

hi def link tdocNumber Number
hi def link tdocLang            PreProc
hi def link tdocNodeName        Identifier
hi def link tdocNodeType        PreProc
hi def link tdocAttributeName   Special
hi def link tdocAttributeValue  String

hi def link tdocHTML            Special
hi def link tdocHTMLStruct      Statement

let b:current_syntax = "tdoc"
" EOF
