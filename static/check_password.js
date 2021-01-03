function check_passwords_before_submit() {
    var passwordInput = document.querySelector('#input-password');
    var passwordConfirmInput = document.querySelector('#input-confirm-password');
    if (passwordInput.value == passwordConfirmInput.value) {
        return true;
    } else {
        var error = document.createElement('li');
        error.innerText = "两次密码不一致";
        var errorlist = document.querySelector('.errorlist');
        while (errorlist.children) {
            errorlist.removeChild(errorlist.children[0]);
        }
        errorlist.appendChild(error);
        return false;
    }
}