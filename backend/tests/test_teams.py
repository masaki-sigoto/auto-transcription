import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.models.user import User
from app.models.team import Team, TeamMember, TeamRole


class TestTeamAPI:
    """チームAPIのテスト"""

    @pytest.mark.asyncio
    async def test_create_team(self, client: AsyncClient, test_user: User):
        """チームを作成"""
        response = await client.post(
            "/api/v1/teams",
            json={
                "name": "テストチーム",
                "description": "テスト用のチームです",
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "テストチーム"
        assert data["description"] == "テスト用のチームです"
        assert data["members_count"] == 1  # オーナーが自動追加される

    @pytest.mark.asyncio
    async def test_list_teams(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """チーム一覧を取得"""
        # チームを作成
        team = Team(name="マイチーム")
        db_session.add(team)
        await db_session.flush()

        member = TeamMember(
            team_id=team.id,
            user_id=test_user.id,
            role=TeamRole.OWNER,
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.get("/api/v1/teams")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "マイチーム"

    @pytest.mark.asyncio
    async def test_get_team(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """チーム詳細を取得"""
        team = Team(name="詳細テストチーム")
        db_session.add(team)
        await db_session.flush()

        member = TeamMember(
            team_id=team.id,
            user_id=test_user.id,
            role=TeamRole.OWNER,
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.get(f"/api/v1/teams/{team.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "詳細テストチーム"

    @pytest.mark.asyncio
    async def test_get_team_not_member(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """メンバーでないチームへのアクセス"""
        team = Team(name="他人のチーム")
        db_session.add(team)
        await db_session.commit()

        response = await client.get(f"/api/v1/teams/{team.id}")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_team(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """チームを更新"""
        team = Team(name="更新前の名前")
        db_session.add(team)
        await db_session.flush()

        member = TeamMember(
            team_id=team.id,
            user_id=test_user.id,
            role=TeamRole.OWNER,
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/teams/{team.id}",
            json={"name": "更新後の名前"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "更新後の名前"

    @pytest.mark.asyncio
    async def test_delete_team(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """チームを削除"""
        team = Team(name="削除予定チーム")
        db_session.add(team)
        await db_session.flush()

        member = TeamMember(
            team_id=team.id,
            user_id=test_user.id,
            role=TeamRole.OWNER,
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.delete(f"/api/v1/teams/{team.id}")
        assert response.status_code == 204


class TestTeamMemberAPI:
    """チームメンバーAPIのテスト"""

    @pytest.mark.asyncio
    async def test_list_members(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """メンバー一覧を取得"""
        team = Team(name="メンバーテストチーム")
        db_session.add(team)
        await db_session.flush()

        member = TeamMember(
            team_id=team.id,
            user_id=test_user.id,
            role=TeamRole.OWNER,
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.get(f"/api/v1/teams/{team.id}/members")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["role"] == "owner"

    @pytest.mark.asyncio
    async def test_invite_member(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """メンバーを招待"""
        team = Team(name="招待テストチーム")
        db_session.add(team)
        await db_session.flush()

        member = TeamMember(
            team_id=team.id,
            user_id=test_user.id,
            role=TeamRole.OWNER,
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.post(
            f"/api/v1/teams/{team.id}/invite",
            json={
                "email": "newmember@example.com",
                "role": "member",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["email"] == "newmember@example.com"
        assert "invite_link" in data


class TestCommentAPI:
    """コメントAPIのテスト"""

    @pytest.mark.asyncio
    async def test_add_comment(
        self,
        client: AsyncClient,
        test_transcription_with_segments,
    ):
        """コメントを追加"""
        response = await client.post(
            f"/api/v1/teams/transcriptions/{test_transcription_with_segments.id}/comments",
            json={
                "content": "これは重要なポイントです",
                "timestamp_ms": "5000",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["content"] == "これは重要なポイントです"
        assert data["is_resolved"] is False

    @pytest.mark.asyncio
    async def test_list_comments(
        self,
        client: AsyncClient,
        test_transcription_with_segments,
    ):
        """コメント一覧を取得"""
        # コメントを追加
        await client.post(
            f"/api/v1/teams/transcriptions/{test_transcription_with_segments.id}/comments",
            json={"content": "コメント1"},
        )
        await client.post(
            f"/api/v1/teams/transcriptions/{test_transcription_with_segments.id}/comments",
            json={"content": "コメント2"},
        )

        response = await client.get(
            f"/api/v1/teams/transcriptions/{test_transcription_with_segments.id}/comments"
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 2
