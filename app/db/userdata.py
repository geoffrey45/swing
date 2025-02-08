from dataclasses import asdict
import datetime
from typing import Any, Literal
from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
    String,
    and_,
    delete,
    func,
    insert,
    select,
    update,
)

from sqlalchemy.orm import Mapped, mapped_column

from app.db.engine import DbEngine
from app.db.utils import (
    favorites_to_dataclass,
    playlist_to_dataclass,
    playlists_to_dataclasses,
    plugin_to_dataclass,
    plugin_to_dataclasses,
    similar_artist_to_dataclass,
    similar_artists_to_dataclass,
    tracklog_to_dataclass,
    tracklog_to_dataclasses,
    user_to_dataclass,
    user_to_dataclasses,
)

from app.db import Base
from app.models.mix import Mix
from app.utils.auth import get_current_userid, hash_password


class UserTable(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    image: Mapped[str] = mapped_column(String(), nullable=True)
    password: Mapped[str] = mapped_column(String())
    username: Mapped[str] = mapped_column(String(), index=True)
    roles: Mapped[list[str]] = mapped_column(JSON(), default_factory=lambda: ["user"])
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSON(), nullable=True, default_factory=dict
    )

    @classmethod
    def get_all(cls):
        result = cls.execute(select(cls))
        return user_to_dataclasses(result.fetchall())

    @classmethod
    def insert_default_user(cls):
        user = {
            "username": "admin",
            "password": hash_password("admin"),
            "roles": ["admin"],
        }

        return cls.insert_one(user)

    @classmethod
    def insert_guest_user(cls):
        user = {
            "username": "guest",
            "password": hash_password("guest"),
            "roles": ["guest"],
        }

        return cls.insert_one(user)

    @classmethod
    def get_by_id(cls, id: int):
        with DbEngine.manager() as conn:
            result = conn.execute(select(cls).where(cls.id == id))
            res = result.fetchone()

            if res:
                return user_to_dataclass(res)

    @classmethod
    def get_by_username(cls, username: str):
        with DbEngine.manager() as conn:
            result = conn.execute(select(cls).where(cls.username == username))
            res = result.fetchone()

            if res:
                return user_to_dataclass(res)

    @classmethod
    def update_one(cls, user: dict[str, Any]):
        with DbEngine.manager(commit=True) as conn:
            conn.execute(update(cls).where(cls.id == user["id"]).values(user))

    @classmethod
    def remove_by_username(cls, username: str):
        return cls.execute(delete(cls).where(cls.username == username), commit=True)


class PluginTable(Base):
    __tablename__ = "plugin"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(), unique=True)
    active: Mapped[bool] = mapped_column(Boolean())
    settings: Mapped[dict[str, Any]] = mapped_column(JSON())
    extra: Mapped[dict[str, Any]] = mapped_column(JSON(), nullable=True)

    @classmethod
    def get_all(cls):
        return plugin_to_dataclasses(cls.all())

    @classmethod
    def activate(cls, name: str, value: bool):
        return cls.execute(
            update(cls).where(cls.name == name).values(active=value), commit=True
        )

    @classmethod
    def get_by_name(cls, name: str):
        result = cls.execute(select(cls).where(cls.name == name))
        return plugin_to_dataclass(result.fetchone())

    @classmethod
    def update_settings(cls, name: str, settings: dict[str, Any]):
        return cls.execute(
            update(cls).where(cls.name == name).values(settings=settings), commit=True
        )


class SimilarArtistTable(Base):
    __tablename__ = "notlastfm_similar_artists"

    id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    artisthash: Mapped[str] = mapped_column(String(), index=True)
    similar_artists: Mapped[dict[str, str]] = mapped_column(JSON())

    @classmethod
    def get_all(cls):
        with DbEngine.manager() as conn:
            result = conn.execute(select(cls))
            return similar_artists_to_dataclass(result.fetchall())

    @classmethod
    def exists(cls, artisthash: str):
        """
        Check whether an artisthash exists in the database.
        """

        with DbEngine.manager() as conn:
            result = conn.execute(
                select(cls.artisthash).where(cls.artisthash == artisthash)
            )
            return result.fetchone() is not None

    @classmethod
    def get_by_hash(cls, artisthash: str):
        """
        Get a single artist by hash.
        """

        with DbEngine.manager() as conn:
            result = conn.execute(select(cls).where(cls.artisthash == artisthash))
            result = result.fetchone()

            if result:
                return similar_artist_to_dataclass(result)


class FavoritesTable(Base):
    __tablename__ = "favorite"

    id: Mapped[int] = mapped_column(primary_key=True)
    hash: Mapped[str] = mapped_column(String(), unique=True)
    type: Mapped[str] = mapped_column(String(), index=True)
    timestamp: Mapped[int] = mapped_column(Integer(), index=True)
    userid: Mapped[int] = mapped_column(
        Integer(), ForeignKey("user.id", ondelete="cascade"), default=1, index=True
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSON(), nullable=True, default_factory=dict
    )

    @classmethod
    def get_all(cls, with_user: bool = False):
        with DbEngine.manager() as conn:
            if with_user:
                result = conn.execute(
                    select(cls).where(cls.userid == get_current_userid())
                )
            else:
                result = conn.execute(select(cls))
            return favorites_to_dataclass(result.fetchall())

    @classmethod
    def insert_item(cls, item: dict[str, Any]):
        item["timestamp"] = int(datetime.datetime.now().timestamp())
        item["userid"] = get_current_userid()

        with DbEngine.manager(commit=True) as conn:
            conn.execute(insert(cls).values(item))

    @classmethod
    def remove_item(cls, item: dict[str, Any]):
        with DbEngine.manager(commit=True) as conn:
            conn.execute(
                delete(cls).where(
                    (cls.hash == item["hash"]) & (cls.type == item["type"])
                )
            )

    @classmethod
    def check_exists(cls, hash: str, type: str):
        result = cls.execute(select(cls).where((cls.hash == hash) & (cls.type == type)))
        return result.fetchone() is not None

    @classmethod
    def get_all_of_type(cls, type: str, start: int, limit: int):
        result = cls.execute(
            select(cls)
            # .select_from(join(table, cls, field == cls.hash))
            .where(and_(cls.type == type, cls.userid == get_current_userid()))
            .order_by(cls.timestamp.desc())
            .offset(start)
            # INFO: If start is 0, fetch all so we can get the total count
            .limit(limit if start != 0 else None)
        )

        res = result.fetchall()

        if start == 0:
            # if limit == -1, return all
            if limit == -1:
                limit = len(res)

            return res[:limit], len(res)

        return res, -1

    @classmethod
    def get_fav_tracks(cls, start: int, limit: int):
        result, total = cls.get_all_of_type("track", start, limit)
        return favorites_to_dataclass(result), total

    @classmethod
    def get_fav_albums(cls, start: int, limit: int):
        result, total = cls.get_all_of_type("album", start, limit)
        return favorites_to_dataclass(result), total

    @classmethod
    def get_fav_artists(cls, start: int, limit: int):
        result, total = cls.get_all_of_type("artist", start, limit)
        return favorites_to_dataclass(result), total

    @classmethod
    def count_favs_in_period(cls, start_time: int, end_time: int):
        result = cls.execute(
            select(func.count(cls.id))
            .where((cls.userid == get_current_userid()))
            .where(and_(cls.timestamp >= start_time, cls.timestamp <= end_time))
        )

        result = result.fetchone()

        if result:
            return result[0]

        return 0


class ScrobbleTable(Base):
    __tablename__ = "scrobble"

    id: Mapped[int] = mapped_column(primary_key=True)
    trackhash: Mapped[str] = mapped_column(String(), index=True)
    duration: Mapped[int] = mapped_column(Integer())
    timestamp: Mapped[int] = mapped_column(Integer())
    source: Mapped[str] = mapped_column(String())
    userid: Mapped[int] = mapped_column(
        Integer(), ForeignKey("user.id", ondelete="cascade"), index=True
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSON(), nullable=True, default_factory=dict
    )

    @classmethod
    def add(cls, item: dict[str, Any]):
        item["userid"] = get_current_userid()
        return cls.insert_one(item)

    @classmethod
    def get_all(cls, start: int, limit: int | None = None, userid: int | None = None):
        result = cls.execute(
            select(cls)
            .where(cls.userid == (userid if userid else get_current_userid()))
            .order_by(cls.timestamp.desc())
            .offset(start)
            .limit(limit)
        )

        return tracklog_to_dataclasses(result.fetchall())

    @classmethod
    def get_all_in_period(cls, start_time: int, end_time: int, userid: int | None):
        # UserId will be None if function is called from the API
        # In that case, we use the request userid
        if userid is None:
            userid = get_current_userid()

        result = cls.execute(
            select(cls)
            .where(cls.userid == userid)
            .where(and_(cls.timestamp >= start_time, cls.timestamp <= end_time))
            .order_by(cls.timestamp.desc())
        )
        return tracklog_to_dataclasses(result.fetchall())

    @classmethod
    def get_last_entry(cls, userid: int):
        result = cls.execute(
            select(cls).where(cls.userid == userid).order_by(cls.timestamp.desc())
        )
        return tracklog_to_dataclass(result.fetchone())


class PlaylistTable(Base):
    __tablename__ = "playlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(), index=True)
    last_updated: Mapped[int] = mapped_column(Integer())
    image: Mapped[str] = mapped_column(String(), nullable=True)
    userid: Mapped[int] = mapped_column(
        Integer(), ForeignKey("user.id", ondelete="cascade")
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSON())
    trackhashes: Mapped[list[str]] = mapped_column(JSON(), default_factory=list)
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSON(), nullable=True, default_factory=dict
    )

    @classmethod
    def get_all(cls, current_user: bool = True):
        if current_user:
            result = cls.execute(select(cls).where(cls.userid == get_current_userid()))
        else:
            result = cls.execute(select(cls))

        return playlists_to_dataclasses(result)

    @classmethod
    def add_one(cls, playlist: dict[str, Any]):
        playlist["userid"] = get_current_userid()
        result = cls.insert_one(playlist)
        return result.lastrowid

    @classmethod
    def check_exists_by_name(cls, name: str):
        result = cls.execute(
            select(cls).where((cls.name == name) & (cls.userid == get_current_userid()))
        )
        return result.fetchone() is not None

    @classmethod
    def append_to_playlist(cls, id: int, trackhashes: list[str]):
        dbtrackhashes = cls.get_trackhashes(id) or []
        trackhashes = list(set(dbtrackhashes).union(set(trackhashes)))

        return cls.execute(
            update(cls)
            .where((cls.id == id) & (cls.userid == get_current_userid()))
            .values(trackhashes=trackhashes),
            commit=True,
        )

    @classmethod
    def get_trackhashes(cls, id: int):
        result = cls.execute(
            select(cls.trackhashes).where(
                (cls.id == id) & (cls.userid == get_current_userid())
            )
        )
        result = result.fetchone()
        if result:
            return result[0]

    @classmethod
    def remove_from_playlist(cls, id: int, trackhashes: list[dict[str, Any]]):
        # INFO: Get db trackhashes
        dbtrackhashes = cls.get_trackhashes(id)
        if dbtrackhashes:
            for item in trackhashes:
                if dbtrackhashes.index(item["trackhash"]) == item["index"]:
                    dbtrackhashes.remove(item["trackhash"])

            return cls.execute(
                update(cls)
                .where((cls.id == id) & (cls.userid == get_current_userid()))
                .values(trackhashes=dbtrackhashes),
                commit=True,
            )

    @classmethod
    def get_by_id(cls, id: int):
        result = cls.execute(
            select(cls).where((cls.id == id) & (cls.userid == get_current_userid()))
        )
        result = result.fetchone()
        if result:
            return playlist_to_dataclass(result)

    @classmethod
    def update_one(cls, id: int, playlist: dict[str, Any]):
        return cls.execute(
            update(cls)
            .where((cls.id == id) & (cls.userid == get_current_userid()))
            .values(playlist),
            commit=True,
        )

    @classmethod
    def update_settings(cls, id: int, settings: dict[str, Any]):
        return cls.execute(
            update(cls)
            .where((cls.id == id) & (cls.userid == get_current_userid()))
            .values(settings=settings),
            commit=True,
        )

    @classmethod
    def remove_image(cls, id: int):
        return cls.execute(
            update(cls)
            .where((cls.id == id) & (cls.userid == get_current_userid()))
            .values(image=None),
            commit=True,
        )


class LibDataTable(Base):
    __tablename__ = "artistdata"

    id: Mapped[int] = mapped_column(primary_key=True)
    itemhash: Mapped[str] = mapped_column(String(), unique=True, index=True)
    itemtype: Mapped[str] = mapped_column(String())
    color: Mapped[str] = mapped_column(String(), nullable=True)
    bio: Mapped[str] = mapped_column(String(), nullable=True)
    info: Mapped[dict[str, Any]] = mapped_column(JSON(), nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSON(), nullable=True, default_factory=dict
    )

    @classmethod
    def update_one(cls, hash: str, data: dict[str, Any]):
        return cls.execute(
            update(cls).where(cls.itemhash == hash).values(data), commit=True
        )

    @classmethod
    def find_one(cls, hash: str, type: Literal["album", "artist"]):
        result = cls.execute(
            select(cls).where((cls.itemhash == type + hash) & (cls.itemtype == type))
        )
        return result.fetchone()

    @classmethod
    def get_all_colors(cls, type: str) -> list[dict[str, str]]:
        result = cls.execute(
            select(cls.itemhash, cls.color).where(cls.itemtype == type)
        )
        return [{"itemhash": r[0].replace(type, ''), "color": r[1]} for r in result.fetchall()]


class MixTable(Base):
    __tablename__ = "mix"

    id: Mapped[int] = mapped_column(primary_key=True)
    mixid: Mapped[str] = mapped_column(String(), index=True)
    title: Mapped[str] = mapped_column(String())
    description: Mapped[str] = mapped_column(String())
    timestamp: Mapped[int] = mapped_column(Integer())
    sourcehash: Mapped[str] = mapped_column(String(), unique=True, index=True)
    userid: Mapped[int] = mapped_column(
        Integer(), ForeignKey("user.id", ondelete="cascade"), index=True
    )
    saved: Mapped[bool] = mapped_column(Boolean(), default=False)
    tracks: Mapped[list[str]] = mapped_column(JSON(), default_factory=list)
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSON(), nullable=True, default_factory=dict
    )

    @classmethod
    def get_all(cls, with_userid: bool = False):
        if with_userid:
            result = cls.execute(
                select(cls)
                .where(cls.userid == get_current_userid())
                .order_by(cls.timestamp.desc())
            )
        else:
            result = cls.execute(select(cls).order_by(cls.timestamp.desc()))

        return Mix.mixes_to_dataclasses(result.fetchall())

    @classmethod
    def get_by_sourcehash(cls, sourcehash: str):
        result = cls.execute(select(cls).where(cls.sourcehash == sourcehash))

        res = result.fetchone()
        if res:
            return Mix.mix_to_dataclass(res)

    @classmethod
    def get_by_mixid(cls, mixid: str):
        result = cls.execute(select(cls).where(cls.mixid == mixid))
        res = result.fetchone()
        if res:
            return Mix.mix_to_dataclass(res)

    @classmethod
    def insert_one(cls, mix: Mix):
        mixdict = asdict(mix)
        mixdict["mixid"] = mix.id
        del mixdict["id"]

        return cls.execute(insert(cls).values(mixdict), commit=True)

    @classmethod
    def update_one(cls, mixid: str, mix: Mix):
        mixdict = asdict(mix)
        mixdict["mixid"] = mix.id
        del mixdict["id"]

        return cls.execute(
            update(cls)
            .where(
                and_(
                    cls.mixid == mixid,
                    cls.sourcehash == mix.sourcehash,
                    cls.userid == get_current_userid(),
                )
            )
            .values(mixdict),
            commit=True,
        )

    @classmethod
    def save_artist_mix(cls, sourcehash: str):
        """
        Toggles the saved status of an artist mix.
        """

        mix = cls.get_by_sourcehash(sourcehash)

        if not mix:
            return False

        mix.saved = not mix.saved
        cls.update_one(mix.id, mix)

        return mix.saved

    @classmethod
    def get_saved_track_mixes(cls):
        """
        Return all mixes that have the extra.trackmix_saved set to True.
        """

        result = cls.execute(select(cls).where(cls.extra.c.trackmix_saved == True))
        return Mix.mixes_to_dataclasses(result.fetchall())

    @classmethod
    def save_track_mix(cls, sourcehash: str):
        """
        Toggles the property extra.trackmix_saved to True.
        """

        mix = cls.get_by_sourcehash(sourcehash)
        if not mix:
            return False

        mix.extra["trackmix_saved"] = not mix.extra.get("trackmix_saved", False)
        cls.update_one(mix.id, mix)

        return mix.extra["trackmix_saved"]


class PageTable(Base):
    __tablename__ = "page"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(), index=True)
    userid: Mapped[int] = mapped_column(
        Integer(), ForeignKey("user.id", ondelete="cascade"), index=True
    )
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON(), default_factory=list)
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSON(), nullable=True, default_factory=dict
    )

    @classmethod
    def to_dict(cls, entry: Any) -> dict[str, Any]:
        return entry._asdict()

    @classmethod
    def get_all(cls):
        result = cls.execute(select(cls).where(cls.userid == get_current_userid()))
        return [cls.to_dict(entry) for entry in result.fetchall()]

    @classmethod
    def get_by_id(cls, id: int):
        result = cls.execute(
            select(cls).where(and_(cls.id == id, cls.userid == get_current_userid()))
        )
        return cls.to_dict(result.fetchone())

    @classmethod
    def delete_by_id(cls, id: int):
        return cls.execute(
            delete(cls).where(and_(cls.id == id, cls.userid == get_current_userid())),
            commit=True,
        )

    @classmethod
    def update_items(cls, id: int, items: list[dict[str, Any]]):
        return cls.execute(
            update(cls)
            .where(and_(cls.id == id, cls.userid == get_current_userid()))
            .values(items=items),
            commit=True,
        )

    @classmethod
    def update_one(cls, payload: dict[str, Any]):
        return cls.execute(
            update(cls)
            .where(and_(cls.id == payload["id"], cls.userid == get_current_userid()))
            .values(payload),
            commit=True,
        )
