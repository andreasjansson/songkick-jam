function submit() {
    var username = $('#username').val();
    var location = $('#location').val();

    $('#results').html('<p id="loading">Loading, please wait!</p>');
    fetchPage(1, username, location);

    return false;
}

function fetchPage(page, username, location) {
    $.get('/results', {username: username, location: location, page: page})
        .done(function(html) {
            $("#results").html(html);
            if (!$('#loading-complete').length) {
                fetchPage(page + 1, username, location);
            }
        })
        .fail(function() {
            alert("Something went wrong!");
        });
}

$(function() {
    $('#form').submit(submit);
});
