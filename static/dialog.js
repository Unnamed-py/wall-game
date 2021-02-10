
function open_dialog(title, content, buttons) {
    var dialog = document.querySelector('.dialog');
    document.querySelector('.dialog .dialog-title').innerText = title;
    document.querySelector('.dialog .dialog-content').innerHTML = '';
    if (typeof content == 'string') {
        document.querySelector('.dialog .dialog-content').innerText = content;
    } else {
        document.querySelector('.dialog .dialog-content').appendChild(content);
    }
    var button_wrapper = document.querySelector('.dialog .dialog-button-wrapper');
    while (button_wrapper.children.length > 0) {
        button_wrapper.removeChild(button_wrapper.children[0]);
    }
    for (var i = 0; i < buttons.length; i++) {
        var button = document.createElement('button');
        button.classList.add('button');
        if (i == 0) {
            button.classList.add('default');
        }
        button.innerText = buttons[i].text;
        button.addEventListener('click', buttons[i].callback);
        button_wrapper.appendChild(button);
    }
    dialog.classList.add('dialog-open');
}

function close_dialog() {
    document.querySelector('.dialog').classList.remove('dialog-open');
}