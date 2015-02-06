var fetching = false;

function submit() {
    if (fetching)
        return false;

    fetching = true;

    var username = $('#username').val();
    var location = $('#location').val();

    $('#results').html('<p id="loading">Loading, please wait!</p>');
    window.history.pushState(null, null, "/results?username=" + username + "&location=" + location);
    fetchPage(1, username, location);

    return false;
}

function fetchPage(page, username, location) {
    $.get('/results', {username: username, location: location, page: page})
        .done(function(html) {
            $("#results").html(html);
            if ($('#loading-complete').length) {
                fetching = false;
            }
            else {
                fetchPage(page + 1, username, location);
            }
        })
        .fail(function() {
            fetching = false;
            alert("Something went wrong!");
        });
}

$(function() {
    $('#form').submit(submit);
});
