# Rock, Paper, Sand! the Media Tracker

Rock, Paper, Sand! is a text-based media tracker for TV shows, movies, books,
plays, and other types of media. It supports advanced filtering for things like
showing which media is available for free at home (from streaming services,
physical copies, or whatever else), which is available elsewhere (e.g., at the
library or in a theater), and which is unavailable.

For an example of what it can do, see [an example config
file](examples/basic.config.yaml), the [output from that config
file](examples/basic.output.yaml), and other examples in the same directory. For
more documentation on the config file format, see [the schema
definition](rock_paper_sand/proto/config.proto).

## Installation

1.  Install the [protobuf compiler](https://grpc.io/docs/protoc-installation/)
    and [pipx](https://pypa.github.io/pipx/).
1.  `pipx install git+https://github.com/dseomn/rock-paper-sand.git`

## What's with the name?

Rock, paper, and sand are all used in different types of physical filters, and
filtering is one of the main focuses of this program.

## Supported use cases

*   Keep track of done, partially done, and to-do media, including obscure media
    that isn't in public databases.
*   Keep track of groups of media of different types. E.g., if you want to read
    a book series, watch the movie series and TV shows based on it, see the
    musical based on the first movie, and read the comic book continuation of
    the TV show, you can keep track of all of those in the same place.
*   Filter that media based on:
    *   Whether it's done, partially done, or to-do.
    *   Whether it's fully released, ongoing, or unreleased, using data from
        [Wikidata](https://www.wikidata.org/).
    *   What streaming services it's available on or if it's currently in
        theaters, using [JustWatch](https://www.justwatch.com/)'s unofficial
        API. This filter also adds extra information to the output to show where
        the media is available, and if only some episodes are available, how
        many.
    *   Custom string field matching. E.g., you can put "borrow from the
        library" in the `customAvailability` field, and filter on that to show
        media that's at the library (possibly excluding media that's also on a
        streaming service you have). Or you can put an
        [archive.org](https://archive.org/) URL for an old public domain movie,
        and include that in a filter for content that's available for free. Or
        you can include the release year in the media name, and filter on media
        released in a range of years.
    *   Custom arbitrary JSON data matching, using
        [JMESPath](https://jmespath.org/) to select which data matches. The data
        can also optionally be validated with [JSON
        Schema](https://json-schema.org/) to catch typos.
    *   Logical combinations of any of the above, including `and`, `or`, and
        `not`.
*   Group results by keys provided by filters. E.g., it's possible to filter for
    media on streaming services that you don't already have, and group the
    result by streaming service, in order to see which streaming service it
    might make sense to subscribe to.
*   Find related media, using data from Wikidata. E.g., find out when a movie
    you liked has a new sequel/remake, or find the book it's based on. Or find
    all media within a media franchise or fictional universe.
*   Print the results to the console in reports.
*   Send email notifications when one of those reports changes.
*   Enforce some conditions on the list of media. E.g., if you want to keep the
    list sorted, that can be checked automatically. Or if you want to make sure
    that all media has a name ending in " (YYYY)" where "YYYY" is the release
    year, you can do that too. (Doing that can help prevent bugs in filters that
    try to parse the media name.)

## Wishlist

*   Better support for filtering based on completeness. E.g., filtering for a TV
    show where all episodes are available, or filtering for a book series where
    the final book has already been released.
*   Integration with public libraries' APIs if possible, to automatically find
    which media can be borrowed from the library.

## Disclaimers

*   This has not been designed to be secure against malicious config files or
    state files. If you write your config file yourself and run the code
    locally, it should hopefully be fine. But if you want to integrate this code
    into a web application or something where multiple remote users can create
    config files that are used by the same local user, it might be worth
    thinking through the security implications first.
*   See also [a disclaimer about JustWatch's unofficial
    API](https://github.com/dawoudt/JustWatchAPI#disclaimer).
