var publicKey = null;
(function () {
    var request = new XMLHttpRequest();
    var publicKeyUrl = /(https?:\/\/[^\/]+?)(\/|$)/.exec(location.href)[1] + '/static/public_key.pem';
    request.open('GET', publicKeyUrl);
    request.send();
    request.onload = function (e) {
        if (request.status == 200) {
            publicKey = request.responseText;
        }
    }
})();


function encrypt_password_before_submit() {
    if (publicKey == null) {
        return false;
    } else {
        var passwordInputs = document.querySelectorAll('form input[type="password"]');
        var jsEncrypt = new JSEncrypt();
        jsEncrypt.setPublicKey(publicKey);
        for (var i = 0; i < passwordInputs.length; i++) {
            if (passwordInputs[i].value != '') {
                passwordInputs[i].value = jsEncrypt.encrypt(passwordInputs[i].value);
            }
        }
        return true;
    }
}
