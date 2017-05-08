import logging
import re
import unicodedata
from datetime import date
from enum import Enum
from typing import Any, Iterable
from typing import List, Optional, Dict
from typing import Set
from property_manager import lazy_property, cached_property
from represent import autorepr


class Serializable(object):
    def serialize(self) -> Any:
        raise NotImplementedError()

    @classmethod
    def deserialize(self, d):
        raise NotImplementedError()


def serialize_iterable(list_of_objects: List[Serializable]) -> List[Any]:
    return [obj.serialize() for obj in list_of_objects]


def deserialize_list(cls, list_of_data: List[Any]) -> List[Serializable]:
    return [cls.deserialize(data) for data in list_of_data]


def deserialize_set(cls, list_of_data: List[Any]) -> List[Serializable]:
    return set(deserialize_list(cls, list_of_data))


class WorkType(Enum):
    CONFERENCE_PAPER = "conference_paper"
    JOURNAL_PAPER = "journal_paper"
    PATENT = "patent"
    BOOK = "book"
    CHAPTER = "book_chapter"
    NEWS = "news"
    TECH_REPORT = "tech_report"
    ENCYCLOPEDIA = "encyclopedia"
    PHD_THESIS = "phd_thesis"
    MAGAZINE = "magazine"
    STANDARD = "standard"
    MASTER_THESIS = "master_thesis"


@autorepr
class Identifier(Serializable):
    doi_regex = re.compile(
        r'10.\d{4,9}/[-._;()/:A-Z0-9]+')  # implement more http://blog.crossref.org/2015/08/doi-regular-expressions.html

    def __init__(self, key_type: str, key: str):
        self.key = key
        self.key_type = key_type
        self.tuple = self.key_type.lower(), self.key.lower()
        self.hash = hash(self.tuple)
        assert ":" not in self.key_type, "Can't have colon in the identifier key type"

    def __eq__(self, other):
        return self.tuple == other.tuple

    def __hash__(self):
        return self.hash

    def __lt__(self, other):
        assert isinstance(other, Identifier)
        return self.tuple.__lt__(other.tuple)

    def __str__(self):
        return "%s:%s" % (self.key_type, self.key)

    def __repr__(self):
        return "{key_type: '%s', key: '%s'}" % (self.key_type, self.key)

    @classmethod
    def is_DOI(cls, possible_doi) -> bool:
        return cls.doi_regex.match(possible_doi) is not None

    def serialize(self) -> List[str]:
        return str(self)

    @classmethod
    def deserialize(cls, d):
        if isinstance(d, str):
            if d[1] == ':' and "::" in d:
                logging.warning("Rectify %s -> %s",
                                d,
                                Identifier(d.split("::", 1)[0].replace(":", ""),
                                           d.split("::", 1)[1].replace(":", "")))
                return Identifier(d.split("::", 1)[0].replace(":", ""), d.split("::", 1)[1].replace(":", ""))

            return Identifier(d.split(":", 1)[0], d.split(":", 1)[1])
        else:
            return Identifier(d[0], d[1])


@autorepr
class DOI(Identifier):
    def __init__(self, doi: str):
        super(DOI, self).__init__("doi", doi)

    @classmethod
    def deserialize(cls, d):
        return Identifier(d[0], d[1])


@autorepr
class WorkDate(object):
    def __init__(self, year: int, month: Optional[int] = None, day: Optional[int] = None):
        self.year = year
        self.month = month
        self.day = day

    @staticmethod
    def from_date_object(date: date):
        return WorkDate(date.year, date.month, date.day)

    def serialize(self) -> List[str]:
        return [self.year, self.month, self.day]

    @classmethod
    def deserialize(cls, d):
        return WorkDate(d[0], d[1], d[2])

    def __eq__(self, other):
        return (
            self.year == other.year and
            self.month == other.month and
            self.day == other.day)


@autorepr
class Organization(Serializable):
    def __init__(self, name: str, identifiers: List[Identifier] = None,
                 department: Optional[str] = None,
                 city: Optional[str] = None,
                 country: Optional[str] = None,
                 address: Optional[str] = None):
        self.country = country
        self.city = city
        self.department = department
        if identifiers is None:
            identifiers = []
        self.identifiers = identifiers
        self.name = name.strip()  # type: str
        self.alias = {self.name}  # type: Set[str]
        self.address = address
        # if BASIC_EMAIL_REGEX.search(self.name):
        #    logging.info("There seems to have an email address in the organization name %s" % name)

    def __hash__(self):
        if "_hash" in self.__dict__:
            return self._hash
        else:
            self._hash = hash(self.to_tuple)
            return self._hash

    def __eq__(self, other):
        return self.to_tuple.__eq__(other.to_tuple)

    def __lt__(self, other):
        # assert isinstance(other, Keyed)
        return self.to_tuple.__lt__(other.to_tuple)

    def serialize(self) -> Dict:

        m = {"country": self.country,
             "city": self.city,
             "department": self.department,
             "identifiers": serialize_iterable(self.identifiers),
             "name": self.name,
             "address": self.address}
        return m

    @classmethod
    def deserialize(cls, d):
        d["identifiers"] = deserialize_list(Identifier, d["identifiers"])
        return Organization(**d)


class AuthorName(object):
    # match beginining or comma and space, then a work, then a dot, or space or comma
    initial_regex = re.compile(r"(^| |,)(\w)(\.| |$|,)")
    first_name_regex = re.compile(r"\w\w+")
    split_regex = re.compile(r'[^\w]+')
    more_spaces = re.compile(r'(\s+)|([^\w]+)')

    def __init__(self, name):
        self.name = name

    @lazy_property
    def normalized(self):
        # this will replace cases like \xa0 with their corresponding unicode
        norm = unicodedata.normalize("NFKD", self.name).lower()
        parts = norm.replace("-", "").split(",")
        return self.more_spaces.sub(" ", " ".join(reversed(parts)), ).strip()

    @lazy_property
    def tokens(self) -> tuple:
        return tuple(self.split_regex.split(self.normalized))

    @cached_property
    def last_name(self) -> str:
        return self.normalized.split(" ")[-1].strip()

    @cached_property
    def no_last_name(self) -> str:
        return self.normalized[:self.normalized.rfind(" ") + 1].strip()

    @cached_property
    def initials(self) -> List[str]:
        return [m.group(2) for m in self.initial_regex.finditer(self.no_last_name)]

    @cached_property
    def first_name(self) -> Optional[str]:
        m = self.first_name_regex.search(self.no_last_name)
        if m is not None:
            return m.group(0)
        else:
            return None

    @cached_property
    def all_initials(self) -> List[str]:
        all_inits = []
        if self.first_name is not None:
            all_inits.append(self.first_name[:1])
        all_inits.extend(self.initials)
        return all_inits

    @cached_property
    def all_unique_initials(self) -> Set[str]:
        return set(self.all_initials)

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self.name.__eq__(other.name)

    def __repr__(self) -> str:
        return repr(self.name)


class Author(Serializable):
    def __init__(self, name: str = None, email=None,
                 identifiers: Iterable[Identifier] = None, given_name=None, last_name=None):

        if identifiers is None:
            identifiers = []
        self.identifiers = set(identifiers)  # type: Set[Identifier]
        if given_name is not None:
            assert last_name is not None and name is None
            self.name = AuthorName(("%s, %s" % (last_name, given_name)).strip())
        else:
            self.name = AuthorName(name.strip())
        if email is not None:
            self.email = email.strip().lower()
        else:
            self.email = None

    @lazy_property
    def to_tuple(self):
        return self.name, self.email, tuple(self.identifiers)

    def __hash__(self):
        if "_hash" in self.__dict__:
            return self._hash
        else:
            self._hash = hash(self.to_tuple)
            return self._hash

    def __eq__(self, other):
        return self.to_tuple.__eq__(other.to_tuple)

    def __repr__(self):
        return "Author(name=\"%s\", email=\"%s\", identifiers=\"%s\")" % (self.name, self.email, self.identifiers)

    def serialize(self) -> str:
        return {"name": self.name.name,
                "identifiers": serialize_iterable(self.identifiers),
                "email": self.email}

    @classmethod
    def deserialize(cls, d):
        d["identifiers"] = deserialize_list(Identifier, d["identifiers"])
        return Author(**d)


@autorepr
class Work(Serializable):
    def __init__(self,
                 primary_key: Identifier,
                 identifiers: Iterable[Identifier],
                 type: WorkType,
                 title: str,
                 authors: List[Author],
                 work_date: WorkDate,
                 figure_links: List[str] = None):
        if figure_links is None:
            self.figure_links = []
        else:
            self.figure_links = figure_links
        self.primary_key = primary_key
        self.identifiers = set(identifiers)  # type: Set[Identifier]
        assert self.identifiers is None or all([isinstance(i, Identifier) for i in self.identifiers])
        self.type = type
        self.title = title
        self.authors = authors

        self.work_date = work_date
        self.figure_links = figure_links


@autorepr
class PaperContainer(object):
    def __init__(self, title: str, identifiers=None, short_title=None):
        if identifiers is None:
            identifiers = []
        self.identifiers = identifiers
        self.title = title
        self.short_title = short_title

    def serialize(self) -> Any:
        ids = serialize_iterable(self.identifiers)

        return {
            "identifiers": ids,
            "title": self.title,
            "short_title": self.short_title,
        }

    @classmethod
    def deserialize(cls, d):
        try:
            d["identifiers"] = deserialize_list(Identifier, d["identifiers"])
        except:
            logging.exception("Can't deserialize %s", d["identifiers"])
            d["identifiers"] = None
        return PaperContainer(**d)


@autorepr
class Citation(object):
    def __init__(self, reference_text: Optional[str] = None,
                 identifiers: List[Identifier] = None,
                 context: Optional[List[str]] = None,
                 title: Optional[str] = None,
                 container: Optional[PaperContainer] = None,
                 authors: Optional[List[Author]] = None,
                 year: Optional[str] = None,
                 volume: Optional[str] = None,
                 issue: Optional[str] = None,
                 page_numbers: Optional[str] = None,
                 organization: Optional[str] = None,
                 url: Optional[str] = None
                 ):
        self.year = year
        self.container = container
        if authors is None:
            authors = []
        self.authors = authors
        if identifiers is None:
            identifiers = []
        if context is None:
            context = []
        self.context = context
        self.identifiers = set(identifiers)  # type: Set[Identifier]
        self.reference_text = reference_text
        self.title = title
        self.page_numbers = page_numbers
        self.volume = volume
        self.issue = issue
        self.url = url
        self.organization = organization

    def serialize(self) -> Any:
        return {
            "reference_text": self.reference_text,
            "identifiers": serialize_iterable(self.identifiers),
            "context": self.context,
            "title": self.title,
            "container": self.container.serialize() if self.container is not None else None,
            "year": self.year,
            "volume": self.volume,
            "issue": self.issue,
            "page_numbers": self.page_numbers,
            "authors": serialize_iterable(self.authors),
            "url": self.url,
            "organization": self.organization
        }

    @classmethod
    def deserialize(cls, d):
        d["identifiers"] = deserialize_set(Identifier, d["identifiers"])
        d["container"] = PaperContainer.deserialize(d["container"]) if d["container"] is not None else None
        d["authors"] = deserialize_list(Author, d["authors"])

        return Citation(**d)

    def __repr__(self):
        return str([self.identifiers, self.reference_text])


@autorepr
class Paper(Work):
    def __init__(self,
                 primary_key: Identifier,
                 identifiers: Iterable[Identifier],
                 type: WorkType,
                 title: str,
                 work_date: WorkDate,
                 authors: List[Author],
                 author_affiliations: List[List[Organization]],
                 abstract: str,
                 keywords: List[str],
                 references: List[Citation] = None,
                 cited_by: List[Citation] = None,
                 ack: str = None,
                 contents: Dict[str, str] = None,
                 paper_container: Optional[PaperContainer] = None,
                 volume: str = None,
                 issue: str = None,
                 first_page: str = None,
                 last_page: str = None,
                 publisher: str = None,
                 figure_links: List[str] = None):

        super().__init__(primary_key, identifiers, type, title, authors, work_date, figure_links)
        self.last_page = last_page
        self.first_page = first_page
        if contents is None:
            contents = {}
        if cited_by is None:
            cited_by = []
        if references is None:
            references = []
        if keywords is None:
            keywords = []
        self.keywords = keywords  # type: List[str]
        self.abstract = abstract
        self.references = references  # type: Optional[List[Citation]]
        self.cited_by = cited_by  # type: Optional[List[Citation]]
        self.ack = ack  # type: str
        self.contents = contents
        self.paper_container = paper_container  # type: Optional[PaperContainer]
        self.volume = volume
        self.issue = issue
        self.publisher = publisher
        self.author_affiliations = author_affiliations  # type: List[List[Organization]]
        assert len(authors) == len(author_affiliations), "%s author affiliation counts do not match %d != %d" % \
                                                         (self.primary_key, len(authors), len(author_affiliations))
        if self.abstract is None or self.abstract.strip() == "":
            pass
            # logging.warning("%s abstract is empty" % self.primary_key)
        if self.title.strip() == "":
            logging.warning("%s title is empty" % self.primary_key)
        if self.work_date.year is None:
            logging.warning("%s year is empty" % self.primary_key)
            # if self.work_date.month is None:
            #     logging.warning("%s hash no month in the workdate" % self.primary_key)

    def serialize(self) -> Any:
        return {
            "primary_key": Identifier.serialize(self.primary_key),
            "identifiers": serialize_iterable(self.identifiers),
            "type": self.type.value,
            "title": self.title,
            "authors": serialize_iterable(self.authors),
            "work_date": self.work_date.serialize(),
            "figure_links": self.figure_links,
            "author_affiliations": [[aff.serialize() for aff in affs] for affs in self.author_affiliations],
            "abstract": self.abstract,
            "keywords": self.keywords,
            "references": serialize_iterable(self.references),
            "cited_by": serialize_iterable(self.cited_by),
            "ack": self.ack,
            "contents": self.contents,
            "paper_container": self.paper_container.serialize() if self.paper_container is not None else None,
            "volume": self.volume,
            "issue": self.issue,
            "publisher": self.publisher,
            "first_page": self.first_page,
            "last_page": self.last_page,
        }

    @classmethod
    def deserialize(cls, d):

        d["primary_key"] = Identifier.deserialize(d["primary_key"])
        d["identifiers"] = deserialize_list(Identifier, d["identifiers"])
        d["type"] = WorkType(d["type"])
        d["authors"] = deserialize_list(Author, d["authors"])
        d["work_date"] = WorkDate.deserialize(d["work_date"])
        d["author_affiliations"] = [[Organization.deserialize(aff) for aff in affs] for affs in
                                    d["author_affiliations"]]
        d["references"] = deserialize_list(Citation, d["references"])
        d["cited_by"] = deserialize_list(Citation, d["cited_by"])
        if d["paper_container"] is not None:
            d["paper_container"] = PaperContainer.deserialize(d["paper_container"])
        return Paper(**d)

    @classmethod
    def deserialize_mongo_record(cls, d):
        if "_id" in d:
            del d["_id"]
        return Paper.deserialize(d)


if __name__ == "__main__":
    import gzip, msgpack

    with gzip.open("NN_Papers.msgpack.gz", "rb") as nn_papers_out:
        unpacker = msgpack.Unpacker(nn_papers_out, encoding='utf-8')
        for _paper in unpacker:
            # _paper is a python dict object. you can use it directly if you don't want to use the Paper class provided here
            paper = Paper.deserialize(_paper)