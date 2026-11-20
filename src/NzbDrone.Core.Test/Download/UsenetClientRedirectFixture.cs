using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using FluentAssertions;
using Moq;
using NUnit.Framework;
using NzbDrone.Core.Download;
using NzbDrone.Core.Download.Clients.Sabnzbd;
using NzbDrone.Core.Download.Clients.Sabnzbd.Responses;
using NzbDrone.Core.Indexers;
using NzbDrone.Core.Parser.Model;
using NzbDrone.Core.Test.Framework;

namespace NzbDrone.Core.Test.Download
{
    [TestFixture]
    public class UsenetClientRedirectFixture : CoreTest<Sabnzbd>
    {
        private readonly byte[] _bytes = { 1, 2, 3, 4 };
        private ReleaseInfo _release;
        private SabnzbdSettings _settings;

        [SetUp]
        public void Setup()
        {
            _release = new ReleaseInfo { Title = "Some Release", DownloadUrl = "https://indexer.example/download/123" };
            _settings = new SabnzbdSettings();
            Subject.Definition = new DownloadClientDefinition { Settings = _settings };
            Mocker.GetMock<IIndexer>().Setup(x => x.Download(It.IsAny<Uri>())).ReturnsAsync(new IndexerDownloadResponse(_bytes));
            var response = new SabnzbdAddResponse { Ids = new List<string> { "download-id" } };
            Mocker.GetMock<ISabnzbdProxy>().Setup(x => x.DownloadNzb(_bytes, "Some Release.nzb", It.IsAny<string>(), It.IsAny<int>(), _settings)).Returns(response);
            Mocker.GetMock<ISabnzbdProxy>().Setup(x => x.DownloadNzbByUrl(_release.DownloadUrl, It.IsAny<string>(), It.IsAny<int>(), _settings)).Returns(response);
        }

        [Test]
        public async Task proxy_mode_fetches_nzb_before_uploading_to_client()
        {
            var result = await Subject.Download(_release, false, Mocker.GetMock<IIndexer>().Object);

            result.Should().Be("download-id");
            Mocker.GetMock<IIndexer>().Verify(x => x.Download(new Uri(_release.DownloadUrl)), Times.Once());
            Mocker.GetMock<ISabnzbdProxy>().Verify(x => x.DownloadNzb(_bytes, "Some Release.nzb", It.IsAny<string>(), It.IsAny<int>(), _settings), Times.Once());
            Mocker.GetMock<ISabnzbdProxy>().Verify(x => x.DownloadNzbByUrl(It.IsAny<string>(), It.IsAny<string>(), It.IsAny<int>(), It.IsAny<SabnzbdSettings>()), Times.Never());
        }

        [Test]
        public async Task redirect_mode_sends_link_without_fetching_nzb()
        {
            var result = await Subject.Download(_release, true, Mocker.GetMock<IIndexer>().Object);

            result.Should().Be("download-id");
            Mocker.GetMock<IIndexer>().Verify(x => x.Download(It.IsAny<Uri>()), Times.Never());
            Mocker.GetMock<ISabnzbdProxy>().Verify(x => x.DownloadNzbByUrl(_release.DownloadUrl, It.IsAny<string>(), It.IsAny<int>(), _settings), Times.Once());
            Mocker.GetMock<ISabnzbdProxy>().Verify(x => x.DownloadNzb(It.IsAny<byte[]>(), It.IsAny<string>(), It.IsAny<string>(), It.IsAny<int>(), It.IsAny<SabnzbdSettings>()), Times.Never());
        }
    }
}
