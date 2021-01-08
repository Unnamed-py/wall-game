var ws;
var status = 'waiting';
var room_size;
var current_player;
var ws_url;
var waiting_action;
var g_reachable_points;
var chosen_pos;
var current_pos;
var DIRS = ['left', 'right', 'top', 'bottom'];

function put_message(message) {
    var ele = document.createElement('div');
    ele.classList.add('message');
    ele.innerText = message
    var message_display = document.getElementById('message-display');
    message_display.appendChild(ele);
    message_display.scrollTop = message_display.scrollHeight;
}

function set_status(text) {
    document.getElementById('status-display').innerText = {
        waiting: '等待玩家',
        running: '游戏进行中',
        finished: '游戏结束',
        disconnected: '连接断开'
    }[text];
    if (['running', 'waiting', 'finished'].includes(text)) {
        status = text
    }
}

function clear_chosen_status(pos) {
    var ele = game_board.children[pos[0]].children[pos[1]];
    var children = Array.from(ele.children);
    for (var i = 0; i < children.length; i++) {
        if (children[i].classList.contains('wall-dir-option')) {
            ele.removeChild(children[i]);
        }
    }
    ele.classList.remove('cell-chosen');
}

function set_reachable_points(reachable_points) {
    g_reachable_points = reachable_points;
    for (var i = 0; i < reachable_points.length; i++) {
        row = reachable_points[i][0];
        col = reachable_points[i][1];
        game_board.children[row].children[col].classList.add('cell-reachable');
        game_board.children[row].children[col].addEventListener('click', function (e) {
            var row, col;
            row = parseInt(this.id.split('-')[1]);
            col = parseInt(this.id.split('-')[2]);
            var flag = false;
            for (var i = 0; i < g_reachable_points.length; i++) {
                if (g_reachable_points[i][0] == row && g_reachable_points[i][1] == col) {
                    flag = true;
                    break;
                }
            }
            if (!flag) {
                return;
            }
            if (chosen_pos) {
                if (chosen_pos[0] == row && chosen_pos[1] == col) {
                    return;
                }
                clear_chosen_status(chosen_pos);
            }
            chosen_pos = [row, col];
            this.classList.add('cell-chosen');
            for (var i = 0; i < DIRS.length; i++) {
                if (!this.classList.contains('cell-wall-' + DIRS[i])) {
                    var ele = document.createElement('div');
                    ele.classList.add('wall-dir-option');
                    ele.classList.add('wall-dir-option-' + DIRS[i]);
                    ele.addEventListener('click', function (e) {
                        var dir;
                        for (var i = 0; i < DIRS.length; i++) {
                            if (this.classList.contains('wall-dir-option-' + DIRS[i])) {
                                dir = DIRS[i];
                                break;
                            }
                        }
                        ws.send(JSON.stringify({
                            motions: [chosen_pos[0] - current_pos[0], chosen_pos[1] - current_pos[1]],
                            wall_dir: dir
                        }));
                        clear_chosen_status(chosen_pos);
                        clear_reachable_points();
                        waiting_action = false;
                    });
                    this.appendChild(ele);
                }
            }
        });
    }
}

function clear_reachable_points() {
    for (var i = 0; i < g_reachable_points.length; i++) {
        row = g_reachable_points[i][0];
        col = g_reachable_points[i][1];
        game_board.children[row].children[col].classList.remove('cell-reachable');
    }
}

function setup_websocket(url, reconnect = false) {
    ws = new WebSocket(url);
    ws.onmessage = function (e) {
        var data = JSON.parse(e.data);
        if (data.event == 'error') {
            alert(data.message);
            location.href = document.referrer;
        } else if (data.event == 'joined') {
            current_player = data.player;
            put_message('您已加入房间，您的符号是：' + current_player);
        } else if (data.event == 'reconnected') {
            current_player = data.player;
            current_pos = data.pos;
            set_status(data.status);
            put_message('重连成功！');
        } else if (data.event == 'new_player') {
            put_message('符号为 ' + data.player + ' 的玩家已加入房间');
        } else if (data.event == 'game_start') {
            put_message('游戏开始！');
            set_status('running');
            game_board = document.getElementById('game-board');
            for (var i = 0; i < room_size; i++) {
                for (var j = 0; j < room_size; j++) {
                    game_board.children[i].children[j].classList.remove('cell-wall-left');
                    game_board.children[i].children[j].classList.remove('cell-wall-right');
                    game_board.children[i].children[j].classList.remove('cell-wall-top');
                    game_board.children[i].children[j].classList.remove('cell-wall-bottom');
                }
            }
        } else if (data.event == 'game_over') {
            put_message('游戏结束！');
            set_status('finished');
            players_scores = data.result;
            var last_rank, last_score, output = [], rank;
            for (var i = 0; i < players_scores.length; i++) {
                if (players_scores[i][1] == last_score) {
                    rank = last_rank;
                } else {
                    rank = i + 1;
                }
                output.push(rank + '. ' + players_scores[i][0] + ' ' + players_scores[i][1]);
                last_rank = rank;
                last_score = players_scores[i][1];
            }
            put_message('游戏排名：\n' + output.join('\n'));
        } else if (data.event == 'update_game_map') {
            var game_board = document.getElementById('game-board');

            function add_class(cell, class_) {
                if (!cell.classList.contains(class_)) {
                    cell.classList.add(class_);
                }
            }

            for (var i = 0; i < room_size; i++) {
                var row = game_board.children[i];
                for (var j = 0; j < room_size; j++) {
                    var cell = row.children[j];
                    cell.innerText = '';
                    if (data.wall_top[i][j] == '1') {
                        add_class(cell, 'cell-wall-top');
                    }
                    if (data.wall_left[i][j] == '1') {
                        add_class(cell, 'cell-wall-left');
                    }
                    if (data.wall_top[i + 1] == null || data.wall_top[i + 1][j] == '1') {
                        add_class(cell, 'cell-wall-bottom');
                    }
                    if (data.wall_left[i][j + 1] == '1' || data.wall_left[i][j + 1] == null) {
                        add_class(cell, 'cell-wall-right');
                    }
                }
            }
            var row, col, player;
            for (var i = 0; i < data.players_info.length; i++) {
                row = data.players_info[i][0];
                col = data.players_info[i][1];
                player = data.players_info[i][2];
                var ele = document.createElement('span');
                ele.innerText = player;
                ele.classList.add('player-display');
                ele.addEventListener('click', function () {
                    this.parentNode.click();
                })
                game_board.children[row].children[col].appendChild(ele);
                if (player == current_player) {
                    current_pos = [row, col];
                }
            }
        } else if (data.event == 'player_out') {
            if (data.player == current_player) {
                put_message('您（' + data.player + '）已出局');
            } else {
                put_message('玩家 ' + data.player + ' 已出局');
            }
        } else if (data.event == 'ask_player_action') {
            if (!data.message) {
                put_message('轮到您了！')
            } else {
                put_message(data.message + '，请重新操作')
            }
            chosen_pos = undefined;
            game_board = document.getElementById('game-board');
            waiting_action = true;
            var row, col;
            set_reachable_points(data.reachable_points);
        } else if (data.event == 'ask_restarting') {
            ws.send(JSON.stringify({'agree': confirm('重新开始游戏？')}));
        }
    }

    ws.onerror = ws.onclose = function (e) {
        if (e.code == 1000) {
            return;
        }
        set_status('disconnected');
        put_message('连接已断开，正在尝试重连……');
        setup_websocket(url, true);
    }
}

function init_room(size) {
    set_status('waiting');
    game_board = document.getElementById('game-board');
    room_size = size;
    waiting_action = false;
    for (var i = 0; i < room_size; i++) {
        var row = document.createElement('div');
        row.classList.add('row');
        for (var j = 0; j < room_size; j++) {
            var cell = document.createElement('div');
            cell.classList.add('cell');
            cell.id = 'cell-' + i + '-' + j;
            row.appendChild(cell);
        }
        game_board.appendChild(row);
    }
    ws_url = location.href.endsWith('/') ? location.href + 'ws/' : location.href + '/ws/';
    ws_url = ws_url.replace('http://', 'ws://').replace('https://', 'wss://');
    setup_websocket(ws_url);
    set_status('等待玩家');

    function reset_game_board_size(ev) {
        var boardSize, fontSize;
        game_board = document.querySelector('#game-board');
        if (window.innerWidth <= 800) {
            boardSize = window.innerWidth - 30;
        } else {
            var messageWrapper = document.querySelector('.message-wrapper');
            boardSize = window.innerWidth - messageWrapper.clientWidth - 50;
        }
        fontSize = Math.floor((boardSize / size - 4) / 1.2);
        game_board.style.fontSize = fontSize + 'px';
    }
    reset_game_board_size();
    window.onresize = reset_game_board_size;
}
